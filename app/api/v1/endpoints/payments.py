"""Payment management endpoints with receipt upload"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks, File, UploadFile
import structlog
import boto3
from botocore.exceptions import ClientError
import uuid
import json
from io import BytesIO

from app.schemas.payment import (
    PaymentCreate,
    PaymentResponse,
    PaymentPlan,
    ReceiptUploadResponse,
    TransactionStatus,
    PaymentPlanStatus
)
from app.core.config import settings
from app.services.aws.event_bridge import EventBridgeService
from app.services.aws.api_gateway import api_gateway_service

router = APIRouter()
logger = structlog.get_logger()

# Initialize AWS clients
import os
if settings.AWS_ACCESS_KEY_ID:
    os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
if settings.AWS_SECRET_ACCESS_KEY:
    os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
if settings.AWS_REGION:
    os.environ['AWS_DEFAULT_REGION'] = settings.AWS_REGION

dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
s3_client = boto3.client('s3', region_name=settings.AWS_REGION)
payments_table = dynamodb.Table(settings.DYNAMODB_PAYMENT_RECORDS_TABLE)
invoices_table = dynamodb.Table(settings.DYNAMODB_INVOICES_TABLE)


@router.post("/", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payment: PaymentCreate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Record a payment for an invoice"""
    try:
        # Verify invoice exists
        invoice_response = invoices_table.get_item(Key={'invoice_id': payment.invoice_id})
        if 'Item' not in invoice_response:
            raise HTTPException(status_code=404, detail="Invoice not found")

        invoice = invoice_response['Item']

        # Generate transaction ID
        transaction_id = f"TXN-{uuid.uuid4().hex[:8].upper()}"

        # Prepare payment data
        now = datetime.utcnow().isoformat()
        payment_data = {
            'transaction_id': transaction_id,
            'invoice_id': payment.invoice_id,
            'customer_id': payment.customer_id,
            'amount': payment.amount,
            'currency': payment.currency,
            'payment_method': payment.payment_method,
            'payment_date': payment.payment_date.isoformat(),
            'reference_number': payment.reference_number,
            'notes': payment.notes,
            'status': payment.status,
            'created_at': now,
            'updated_at': now
        }

        # If receipt URL provided, store reference
        if payment.receipt_url:
            payment_data['receipt_url'] = payment.receipt_url

        # Save to DynamoDB
        payments_table.put_item(Item=payment_data)

        # Update invoice payment status
        update_invoice_payment(invoice['invoice_id'], payment.amount)

        # Publish payment received event
        background_tasks.add_task(
            publish_payment_received_event,
            transaction_id,
            payment.invoice_id,
            payment.amount
        )

        return PaymentResponse(
            transaction_id=transaction_id,
            invoice_id=payment.invoice_id,
            customer_id=payment.customer_id,
            amount=payment.amount,
            currency=payment.currency,
            payment_method=payment.payment_method,
            payment_date=payment.payment_date,
            reference_number=payment.reference_number,
            notes=payment.notes,
            status=payment.status,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            receipt_s3_key=None,
            processed_data=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create payment", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-receipt", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    invoice_id: str = Query(..., description="Invoice ID"),
    transaction_id: Optional[str] = Query(None, description="Transaction ID"),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload a payment receipt image to S3"""
    try:
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/pdf', 'application/pdf']
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed types: {allowed_types}"
            )

        # Generate S3 key
        file_extension = file.filename.split('.')[-1]
        s3_key = f"receipts/{invoice_id}/{uuid.uuid4().hex}.{file_extension}"

        # Read file content
        file_content = await file.read()

        # Upload to S3
        s3_client.put_object(
            Bucket=settings.AWS_S3_BUCKET_NAME,
            Key=s3_key,
            Body=file_content,
            ContentType=file.content_type,
            Metadata={
                'invoice_id': invoice_id,
                'transaction_id': transaction_id or '',
                'upload_timestamp': datetime.utcnow().isoformat()
            }
        )

        # Generate presigned URL for access (valid for 24 hours)
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.AWS_S3_BUCKET_NAME, 'Key': s3_key},
            ExpiresIn=86400  # 24 hours
        )

        # Update payment record if transaction_id provided
        if transaction_id:
            payments_table.update_item(
                Key={'transaction_id': transaction_id},
                UpdateExpression="SET receipt_s3_key = :key, updated_at = :now",
                ExpressionAttributeValues={
                    ':key': s3_key,
                    ':now': datetime.utcnow().isoformat()
                }
            )

        # Process receipt using AI via API Gateway
        background_tasks.add_task(
            process_receipt_with_ai,
            s3_key,
            invoice_id,
            transaction_id
        )

        # Publish receipt uploaded event
        background_tasks.add_task(
            publish_receipt_uploaded_event,
            s3_key,
            invoice_id,
            transaction_id
        )

        return ReceiptUploadResponse(
            file_name=file.filename,
            s3_key=s3_key,
            bucket_name=settings.AWS_S3_BUCKET_NAME,
            upload_url=presigned_url,
            uploaded_at=datetime.utcnow(),
            size=len(file_content),
            content_type=file.content_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload receipt", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/receipt/{transaction_id}")
async def get_receipt_url(transaction_id: str):
    """Get presigned URL for receipt"""
    try:
        # Get payment record
        response = payments_table.get_item(Key={'transaction_id': transaction_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Payment not found")

        payment = response['Item']
        if 'receipt_s3_key' not in payment:
            raise HTTPException(status_code=404, detail="No receipt found for this payment")

        # Generate presigned URL
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_S3_BUCKET_NAME,
                'Key': payment['receipt_s3_key']
            },
            ExpiresIn=3600  # 1 hour
        )

        return {
            'transaction_id': transaction_id,
            'receipt_url': presigned_url,
            'expires_in': 3600
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get receipt URL", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-payment-plan")
async def generate_ai_payment_plan(
    customer_id: str,
    request_type: str = "create_plan",
    total_amount: Optional[float] = None,
    requested_months: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Generate AI-powered payment plan via AWS API Gateway"""
    try:
        # Initialize API Gateway service
        await api_gateway_service.initialize()

        # Call AWS API Gateway to generate payment plan
        response = await api_gateway_service.generate_payment_plan(
            customer_id=customer_id,
            request_type=request_type,
            total_amount=total_amount,
            requested_months=requested_months
        )

        logger.info(
            "AI payment plan generated",
            customer_id=customer_id,
            request_type=request_type,
            response=response
        )

        return response

    except Exception as e:
        logger.error("Failed to generate AI payment plan", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment-plan", response_model=PaymentPlan)
async def create_payment_plan(
    plan: PaymentPlan,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Create a payment plan for an invoice"""
    try:
        # Verify invoice exists
        invoice_response = invoices_table.get_item(Key={'invoice_id': plan.invoice_id})
        if 'Item' not in invoice_response:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Generate plan ID
        plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"
        plan.plan_id = plan_id

        # Save payment plan to DynamoDB
        plan_data = plan.dict()
        plan_data['created_at'] = datetime.utcnow().isoformat()

        payments_table.put_item(Item=plan_data)

        # Publish payment plan created event
        background_tasks.add_task(
            publish_payment_plan_created_event,
            plan_id,
            plan.invoice_id,
            plan.customer_id
        )

        return plan
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create payment plan", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payment-plan/{plan_id}", response_model=PaymentPlan)
async def get_payment_plan(plan_id: str):
    """Get payment plan details"""
    try:
        response = payments_table.get_item(Key={'plan_id': plan_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Payment plan not found")

        return PaymentPlan(**response['Item'])
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get payment plan", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/invoice/{invoice_id}/payments")
async def get_invoice_payments(
    invoice_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100)
):
    """Get all payments for an invoice"""
    try:
        # Query payments by invoice_id
        response = payments_table.scan(
            FilterExpression="invoice_id = :invoice_id",
            ExpressionAttributeValues={":invoice_id": invoice_id}
        )

        items = response.get('Items', [])

        # Apply pagination
        paginated_items = items[skip:skip + limit]

        # Convert to response models
        payments = []
        for item in paginated_items:
            payment = PaymentResponse(
                transaction_id=item['transaction_id'],
                invoice_id=item['invoice_id'],
                customer_id=item['customer_id'],
                amount=float(item['amount']),
                currency=item.get('currency', 'USD'),
                payment_method=item['payment_method'],
                payment_date=datetime.fromisoformat(item['payment_date']),
                reference_number=item.get('reference_number'),
                notes=item.get('notes'),
                status=item.get('status', TransactionStatus.SUCCESS),
                created_at=datetime.fromisoformat(item['created_at']),
                updated_at=datetime.fromisoformat(item['updated_at']),
                receipt_s3_key=item.get('receipt_s3_key'),
                processed_data=item.get('processed_data')
            )
            payments.append(payment)

        return {
            'payments': payments,
            'total': len(items),
            'skip': skip,
            'limit': limit
        }
    except Exception as e:
        logger.error("Failed to get invoice payments", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def update_invoice_payment(invoice_id: str, payment_amount: float):
    """Update invoice payment information"""
    try:
        # Get current invoice
        response = invoices_table.get_item(Key={'invoice_id': invoice_id})
        if 'Item' not in response:
            return

        invoice = response['Item']
        current_paid = float(invoice.get('paid_amount', 0))
        total_amount = float(invoice.get('total_amount', 0))

        new_paid = current_paid + payment_amount
        outstanding = max(0, total_amount - new_paid)

        # Determine payment status
        if outstanding == 0:
            payment_status = 'paid'
        elif new_paid > 0:
            payment_status = 'partial'
        else:
            payment_status = 'unpaid'

        # Update invoice
        invoices_table.update_item(
            Key={'invoice_id': invoice_id},
            UpdateExpression="SET paid_amount = :paid, outstanding_amount = :outstanding, payment_status = :status, updated_at = :now",
            ExpressionAttributeValues={
                ':paid': new_paid,
                ':outstanding': outstanding,
                ':status': payment_status,
                ':now': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to update invoice payment: {str(e)}")


async def publish_payment_received_event(transaction_id: str, invoice_id: str, amount: float):
    """Publish payment received event"""
    try:
        event_bridge = EventBridgeService()
        await event_bridge.initialize()

        await event_bridge.publish_event(
            source='billing.payment.received',
            detail_type='Payment Received',
            detail={
                'transaction_id': transaction_id,
                'invoice_id': invoice_id,
                'amount': amount,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to publish payment event: {str(e)}")


async def process_receipt_with_ai(s3_key: str, invoice_id: str, transaction_id: str):
    """Process receipt using AI via API Gateway"""
    try:
        # Initialize API Gateway service
        await api_gateway_service.initialize()

        # Get customer_id from transaction or invoice
        customer_id = None
        if transaction_id:
            # Get customer_id from payment record
            payment_response = payments_table.get_item(Key={'transaction_id': transaction_id})
            if 'Item' in payment_response:
                customer_id = payment_response['Item'].get('customer_id')

        if not customer_id and invoice_id:
            # Get customer_id from invoice
            invoice_response = invoices_table.get_item(Key={'invoice_id': invoice_id})
            if 'Item' in invoice_response:
                customer_id = invoice_response['Item'].get('customer_id')

        if not customer_id:
            logger.error("Could not determine customer_id for receipt processing")
            return

        # Process receipt via API Gateway
        response = await api_gateway_service.process_receipt(
            receipt_image_key=s3_key,
            customer_id=customer_id,
            reference_invoice=invoice_id
        )

        # Update payment record with processed data
        if transaction_id and response:
            payments_table.update_item(
                Key={'transaction_id': transaction_id},
                UpdateExpression="SET processed_data = :data, updated_at = :now",
                ExpressionAttributeValues={
                    ':data': response,
                    ':now': datetime.utcnow().isoformat()
                }
            )

        logger.info(
            "Receipt processed with AI",
            s3_key=s3_key,
            customer_id=customer_id,
            transaction_id=transaction_id,
            response=response
        )

    except Exception as e:
        logger.error(f"Failed to process receipt with AI: {str(e)}")


async def publish_receipt_uploaded_event(s3_key: str, invoice_id: str, transaction_id: str):
    """Publish receipt uploaded event"""
    try:
        event_bridge = EventBridgeService()
        await event_bridge.initialize()

        await event_bridge.publish_event(
            source='billing.receipt.uploaded',
            detail_type='Receipt Uploaded',
            detail={
                's3_key': s3_key,
                'invoice_id': invoice_id,
                'transaction_id': transaction_id,
                'bucket': settings.AWS_S3_BUCKET_NAME,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to publish receipt event: {str(e)}")


async def publish_payment_plan_created_event(plan_id: str, invoice_id: str, customer_id: str):
    """Publish payment plan created event"""
    try:
        event_bridge = EventBridgeService()
        await event_bridge.initialize()

        await event_bridge.publish_event(
            source='billing.payment.plan.created',
            detail_type='Payment Plan Created',
            detail={
                'plan_id': plan_id,
                'invoice_id': invoice_id,
                'customer_id': customer_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to publish payment plan event: {str(e)}")