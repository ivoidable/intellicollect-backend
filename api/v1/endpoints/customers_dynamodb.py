"""Customer endpoints using DynamoDB"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
import structlog
import boto3
from botocore.exceptions import ClientError
import uuid

from schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse
)
from core.config import settings

router = APIRouter()
logger = structlog.get_logger()

# Initialize AWS clients directly
import os
if settings.AWS_ACCESS_KEY_ID:
    os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
if settings.AWS_SECRET_ACCESS_KEY:
    os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
if settings.AWS_REGION:
    os.environ['AWS_DEFAULT_REGION'] = settings.AWS_REGION

dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
customers_table = dynamodb.Table(settings.DYNAMODB_CUSTOMERS_TABLE)
invoices_table = dynamodb.Table(settings.DYNAMODB_INVOICES_TABLE)


async def calculate_customer_outstanding_amount(customer_id: str) -> float:
    """Calculate customer's total outstanding amount from all their invoices"""
    try:
        # Query all invoices for this customer
        response = invoices_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )

        invoices = response.get('Items', [])

        # Sum all outstanding amounts from invoices
        total_outstanding = sum(
            float(invoice.get('outstanding_amount', 0))
            for invoice in invoices
        )

        return total_outstanding
    except Exception as e:
        logger.error(f"Failed to calculate outstanding amount for customer {customer_id}", error=str(e))
        return 0.0


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    search: Optional[str] = None,
):
    """List all customers"""
    logger.info("Getting customers list", skip=skip, limit=limit, search=search)
    try:
        # Build filter expression for search
        scan_kwargs = {}

        if search:
            filter_expression = "contains(#name, :search) OR contains(email, :search)"
            scan_kwargs['FilterExpression'] = filter_expression
            scan_kwargs['ExpressionAttributeValues'] = {":search": search}
            scan_kwargs['ExpressionAttributeNames'] = {'#name': 'name'}

        response = customers_table.scan(**scan_kwargs)
        items = response.get('Items', [])

        # Apply pagination
        paginated_items = items[skip:skip + limit]

        # Convert to response models
        customers = []
        for item in paginated_items:
            # Calculate outstanding amount from invoices
            outstanding_amount = await calculate_customer_outstanding_amount(item['customer_id'])

            customer = CustomerResponse(
                id=item['customer_id'],
                name=item['name'],
                email=item['email'],
                phone=item.get('phone'),
                address=item.get('address'),
                company=item.get('company'),
                industry=item.get('industry'),
                status=item.get('status', 'active'),
                risk_level=item.get('risk_level'),
                created_at=datetime.fromisoformat(item.get('created_at', datetime.utcnow().isoformat())),
                updated_at=datetime.fromisoformat(item.get('updated_at', datetime.utcnow().isoformat())),
                created_date=item.get('created_date'),
                total_invoices=item.get('total_invoices', 0),
                outstanding_amount=outstanding_amount,
                payment_history=item.get('payment_history')
            )
            customers.append(customer)

        logger.info("Successfully retrieved customers", count=len(customers), total=len(items))
        return CustomerListResponse(
            customers=customers,
            total=len(items),
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error("Failed to list customers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer: CustomerCreate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Create a new customer"""
    logger.info("Creating new customer", email=customer.email, name=customer.name)
    try:
        # Generate customer ID
        customer_id = f"CUST-{uuid.uuid4().hex[:8].upper()}"

        # Prepare customer data
        now = datetime.utcnow().isoformat()
        customer_data = {
            'customer_id': customer_id,
            'name': customer.name,
            'email': customer.email,
            'phone': customer.phone,
            'address': customer.address,
            'company': customer.company,
            'industry': customer.industry,
            'status': customer.status,
            'risk_level': customer.risk_level,
            'total_invoices': 0,
            'created_at': now,
            'updated_at': now,
            'created_date': datetime.utcnow().strftime('%Y-%m-%d')
        }

        # Save to DynamoDB
        customers_table.put_item(Item=customer_data)

        logger.info("Customer created successfully", customer_id=customer_id, email=customer.email)

        # Calculate outstanding amount from invoices (will be 0 for new customer)
        outstanding_amount = await calculate_customer_outstanding_amount(customer_id)

        return CustomerResponse(
            id=customer_id,
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            address=customer.address,
            company=customer.company,
            industry=customer.industry,
            status=customer.status,
            risk_level=customer.risk_level,
            created_at=datetime.fromisoformat(now),
            updated_at=datetime.fromisoformat(now),
            created_date=datetime.utcnow().strftime('%Y-%m-%d'),
            total_invoices=0,
            outstanding_amount=outstanding_amount,
            payment_history=None
        )
    except Exception as e:
        logger.error("Failed to create customer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: str):
    """Get customer by ID"""
    try:
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Customer not found")

        item = response['Item']

        # Calculate outstanding amount from invoices
        outstanding_amount = await calculate_customer_outstanding_amount(item['customer_id'])

        return CustomerResponse(
            id=item['customer_id'],
            name=item['name'],
            email=item['email'],
            phone=item.get('phone'),
            address=item.get('address'),
            company=item.get('company'),
            industry=item.get('industry'),
            status=item.get('status', 'active'),
            risk_level=item.get('risk_level'),
            created_at=datetime.fromisoformat(item.get('created_at', datetime.utcnow().isoformat())),
            updated_at=datetime.fromisoformat(item.get('updated_at', datetime.utcnow().isoformat())),
            created_date=item.get('created_date'),
            total_invoices=item.get('total_invoices', 0),
            outstanding_amount=outstanding_amount,
            payment_history=item.get('payment_history')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get customer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_update: CustomerUpdate
):
    """Update customer information"""
    try:
        # Check if customer exists
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Prepare update expression
        update_expression = "SET updated_at = :updated_at"
        expression_attribute_values = {":updated_at": datetime.utcnow().isoformat()}

        # Add fields to update
        update_fields = customer_update.dict(exclude_unset=True)
        for field, value in update_fields.items():
            if value is not None:
                if field == 'name':
                    update_expression += f", #name = :{field}"
                else:
                    update_expression += f", {field} = :{field}"
                expression_attribute_values[f":{field}"] = value

        # Build expression attribute names if name is being updated
        expression_attribute_names = None
        if 'name' in update_fields:
            expression_attribute_names = {'#name': 'name'}

        # Update in DynamoDB
        update_kwargs = {
            'Key': {'customer_id': customer_id},
            'UpdateExpression': update_expression,
            'ExpressionAttributeValues': expression_attribute_values
        }
        if expression_attribute_names:
            update_kwargs['ExpressionAttributeNames'] = expression_attribute_names

        customers_table.update_item(**update_kwargs)

        # Get updated customer
        return await get_customer(customer_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update customer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(customer_id: str):
    """Delete a customer"""
    try:
        # Check if customer exists
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Delete from DynamoDB
        customers_table.delete_item(Key={'customer_id': customer_id})

        logger.info(f"Customer {customer_id} deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete customer", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{customer_id}/assess-risk", status_code=status.HTTP_202_ACCEPTED)
async def trigger_risk_assessment(
    customer_id: str,
    background_tasks: BackgroundTasks
):
    """Trigger risk assessment for customer"""
    try:
        # Check if customer exists
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Customer not found")

        # In production, this would trigger a Lambda function
        # For now, return accepted status
        logger.info(f"Risk assessment triggered for customer {customer_id}")

        return {
            "message": "Risk assessment triggered",
            "customer_id": customer_id,
            "status": "processing"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to trigger risk assessment", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))