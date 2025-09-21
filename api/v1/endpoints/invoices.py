"""Invoice management endpoints using DynamoDB"""

from typing import List, Optional
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
import structlog
import boto3
from botocore.exceptions import ClientError
import uuid
import json

from schemas.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse,
    InvoiceStatus,
    PaymentStatus
)
from core.config import settings
from services.aws.event_bridge import EventBridgeService

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
invoices_table = dynamodb.Table(settings.DYNAMODB_INVOICES_TABLE)
customers_table = dynamodb.Table(settings.DYNAMODB_CUSTOMERS_TABLE)


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    customer_id: Optional[str] = Query(None, description="Filter by customer ID"),
    status: Optional[InvoiceStatus] = Query(None, description="Filter by status"),
    payment_status: Optional[PaymentStatus] = Query(None, description="Filter by payment status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
):
    """List all invoices with optional filtering"""
    logger.info("Listing invoices", customer_id=customer_id, status=status, payment_status=payment_status, skip=skip, limit=limit)
    try:
        # Build filter expression
        filter_expression = None
        expression_attribute_values = {}

        if customer_id:
            filter_expression = "customer_id = :customer_id"
            expression_attribute_values[":customer_id"] = customer_id

        if status:
            status_filter = "invoice_status = :status"
            expression_attribute_values[":status"] = status
            filter_expression = f"{filter_expression} AND {status_filter}" if filter_expression else status_filter

        if payment_status:
            payment_filter = "payment_status = :payment_status"
            expression_attribute_values[":payment_status"] = payment_status
            filter_expression = f"{filter_expression} AND {payment_filter}" if filter_expression else payment_filter

        # Query DynamoDB
        scan_kwargs = {}
        if filter_expression:
            scan_kwargs['FilterExpression'] = filter_expression
            scan_kwargs['ExpressionAttributeValues'] = expression_attribute_values

        response = invoices_table.scan(**scan_kwargs)
        items = response.get('Items', [])

        # Apply pagination
        paginated_items = items[skip:skip + limit]

        # Convert to response model
        invoices = []
        for item in paginated_items:
            invoice = InvoiceResponse(
                invoice_id=item['invoice_id'],
                customer_id=item['customer_id'],
                invoice_date=date.fromisoformat(item.get('invoice_date', item.get('created_timestamp', datetime.utcnow().isoformat())[:10])),
                due_date=date.fromisoformat(item['due_date']),
                amount=float(item.get('amount', 0)),
                total_amount=float(item.get('total_amount', 0)),
                currency=item.get('currency', 'USD'),
                status=item.get('status', InvoiceStatus.DRAFT).lower() if item.get('status') else InvoiceStatus.DRAFT,
                payment_status=item.get('payment_status', PaymentStatus.UNPAID).lower() if item.get('payment_status') else PaymentStatus.UNPAID,
                risk_level=item.get('risk_level'),
                risk_score=item.get('risk_score'),
                created_timestamp=item.get('created_timestamp'),
                paid_amount=float(item.get('paid_amount', 0)),
                outstanding_amount=float(item.get('outstanding_amount', item.get('total_amount', 0))),
                reminder_count=item.get('reminder_count', 0),
                last_reminder_date=item.get('last_reminder_date'),
                payment_date=item.get('payment_date'),
                payment_reference=item.get('payment_reference')
            )
            invoices.append(invoice)

        return InvoiceListResponse(
            invoices=invoices,
            total=len(items),
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error("Failed to list invoices", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice: InvoiceCreate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Create a new invoice"""
    logger.info("Creating invoice", customer_id=invoice.customer_id, amount=invoice.amount, due_date=invoice.due_date)
    try:
        # Verify customer exists
        customer_response = customers_table.get_item(Key={'customer_id': invoice.customer_id})
        if 'Item' not in customer_response:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Generate invoice ID
        invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

        # Prepare invoice data
        now = datetime.utcnow().isoformat()
        from decimal import Decimal
        invoice_data = {
            'invoice_id': invoice_id,
            'customer_id': invoice.customer_id,
            'invoice_date': invoice.invoice_date.isoformat(),
            'due_date': invoice.due_date.isoformat(),
            'amount': Decimal(str(invoice.amount)),
            'total_amount': Decimal(str(invoice.total_amount)),
            'currency': invoice.currency,
            'status': invoice.status,
            'payment_status': invoice.payment_status,
            'risk_level': invoice.risk_level,
            'risk_score': Decimal(str(invoice.risk_score)) if invoice.risk_score else None,
            'paid_amount': Decimal('0'),
            'outstanding_amount': Decimal(str(invoice.total_amount)),
            'reminder_count': 0,
            'created_timestamp': now
        }

        # Save to DynamoDB
        invoices_table.put_item(Item=invoice_data)

        # Publish event to EventBridge
        background_tasks.add_task(
            publish_invoice_created_event,
            invoice_id,
            invoice.customer_id,
            invoice.total_amount
        )

        # Return response
        return InvoiceResponse(
            invoice_id=invoice_id,
            customer_id=invoice.customer_id,
            invoice_date=invoice.invoice_date,
            due_date=invoice.due_date,
            amount=invoice.amount,
            total_amount=invoice.total_amount,
            currency=invoice.currency,
            status=invoice.status,
            payment_status=invoice.payment_status,
            risk_level=invoice.risk_level,
            risk_score=invoice.risk_score,
            created_timestamp=now,
            paid_amount=0,
            outstanding_amount=invoice.total_amount,
            reminder_count=0,
            last_reminder_date=None,
            payment_date=None,
            payment_reference=None
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create invoice", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(invoice_id: str):
    """Get invoice by ID"""
    try:
        response = invoices_table.get_item(Key={'invoice_id': invoice_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Invoice not found")

        item = response['Item']
        return InvoiceResponse(
            invoice_id=item['invoice_id'],
            customer_id=item['customer_id'],
            invoice_date=date.fromisoformat(item.get('invoice_date', item.get('created_timestamp', datetime.utcnow().isoformat())[:10])),
            due_date=date.fromisoformat(item['due_date']),
            amount=float(item.get('amount', 0)),
            total_amount=float(item.get('total_amount', 0)),
            currency=item.get('currency', 'USD'),
            status=item.get('status', InvoiceStatus.DRAFT).lower() if item.get('status') else InvoiceStatus.DRAFT,
            payment_status=item.get('payment_status', PaymentStatus.UNPAID).lower() if item.get('payment_status') else PaymentStatus.UNPAID,
            risk_level=item.get('risk_level'),
            risk_score=item.get('risk_score'),
            created_timestamp=item.get('created_timestamp'),
            paid_amount=float(item.get('paid_amount', 0)),
            outstanding_amount=float(item.get('outstanding_amount', item.get('total_amount', 0))),
            reminder_count=item.get('reminder_count', 0),
            last_reminder_date=item.get('last_reminder_date'),
            payment_date=item.get('payment_date'),
            payment_reference=item.get('payment_reference')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get invoice", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: str,
    invoice_update: InvoiceUpdate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Update an existing invoice"""
    try:
        # Get existing invoice
        response = invoices_table.get_item(Key={'invoice_id': invoice_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Invoice not found")

        existing_item = response['Item']

        # Prepare update expression
        update_expression = "SET updated_at = :updated_at"
        expression_attribute_values = {":updated_at": datetime.utcnow().isoformat()}

        # Add fields to update
        update_fields = invoice_update.dict(exclude_unset=True)
        for field, value in update_fields.items():
            if value is not None:
                if field == 'status':
                    update_expression += f", invoice_status = :{field}"
                elif field == 'issue_date' or field == 'due_date':
                    update_expression += f", {field} = :{field}"
                    expression_attribute_values[f":{field}"] = value.isoformat()
                elif field == 'items':
                    update_expression += f", {field} = :{field}"
                    expression_attribute_values[f":{field}"] = [item.dict() for item in value]
                else:
                    update_expression += f", {field} = :{field}"
                    expression_attribute_values[f":{field}"] = value

        # Update outstanding amount if payment status changed
        if 'payment_status' in update_fields or 'total_amount' in update_fields:
            paid_amount = float(existing_item.get('paid_amount', 0))
            total_amount = update_fields.get('total_amount', existing_item.get('total_amount', 0))
            outstanding = total_amount - paid_amount
            update_expression += ", outstanding_amount = :outstanding_amount"
            expression_attribute_values[":outstanding_amount"] = outstanding

        # Update in DynamoDB
        invoices_table.update_item(
            Key={'invoice_id': invoice_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values
        )

        # Get updated invoice
        return await get_invoice(invoice_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update invoice", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: str):
    """Delete an invoice"""
    try:
        # Check if invoice exists
        response = invoices_table.get_item(Key={'invoice_id': invoice_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Invoice not found")

        # Delete from DynamoDB
        invoices_table.delete_item(Key={'invoice_id': invoice_id})

        logger.info(f"Invoice {invoice_id} deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete invoice", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def publish_invoice_created_event(invoice_id: str, customer_id: str, amount: float):
    """Publish invoice created event to EventBridge"""
    try:
        event_bridge = EventBridgeService()
        await event_bridge.initialize()

        event_data = {
            'invoice_id': invoice_id,
            'customer_id': customer_id,
            'amount': amount,
            'timestamp': datetime.utcnow().isoformat()
        }

        await event_bridge.publish_event(
            source='billing.invoice.created',
            detail_type='Invoice Created',
            detail=event_data
        )

        logger.info(f"Published invoice created event for {invoice_id}")
    except Exception as e:
        logger.error(f"Failed to publish event: {str(e)}")