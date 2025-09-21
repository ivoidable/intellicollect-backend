"""Customer endpoints using DynamoDB"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks, Depends
import structlog

from app.dynamodb.models import Customer
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate, CustomerResponse, CustomerListResponse
from app.services.aws.customer_intelligence import CustomerIntelligenceService
from app.services.event_processor import EventProcessor
from app.core.security import get_current_user

router = APIRouter()
logger = structlog.get_logger()


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    company_id: str = Query(..., description="Company ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    search: Optional[str] = None,
    current_user=Depends(get_current_user)
):
    """List all customers for a company"""
    try:
        repo = CustomerRepository()

        if search:
            # Search customers
            customers = await repo.search(company_id, search, limit)
            return CustomerListResponse(
                customers=[CustomerResponse.from_orm(c) for c in customers],
                total=len(customers),
                skip=skip,
                limit=limit
            )
        else:
            # Get paginated list
            result = await repo.get_by_company(company_id, limit)
            return CustomerListResponse(
                customers=[CustomerResponse.from_orm(c) for c in result['customers']],
                total=result['count'],
                skip=skip,
                limit=limit,
                next_token=result.get('last_evaluated_key')
            )

    except Exception as e:
        logger.error("Failed to list customers", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customers"
        )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: str,
    current_user=Depends(get_current_user)
):
    """Get a specific customer by ID"""
    try:
        repo = CustomerRepository()
        customer = await repo.get_by_id(customer_id)

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        return CustomerResponse.from_orm(customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get customer", customer_id=customer_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer"
        )


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user)
):
    """Create a new customer"""
    try:
        repo = CustomerRepository()

        # Check if email already exists in company
        existing = await repo.get_by_email(customer_data.company_id, customer_data.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this email already exists in the company"
            )

        # Create customer model
        customer = Customer(**customer_data.dict())

        # Save to database
        customer = await repo.create(customer)

        # Trigger AWS customer profile creation
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_created,
            customer_id=customer.id,
            customer_data=customer_data.dict()
        )

        # Trigger initial risk assessment
        intelligence_service = CustomerIntelligenceService()
        background_tasks.add_task(
            intelligence_service.assess_customer_risk,
            customer_id=customer.id
        )

        logger.info("Customer created", customer_id=customer.id)
        return CustomerResponse.from_orm(customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create customer", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer"
        )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: str,
    customer_data: CustomerUpdate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user)
):
    """Update an existing customer"""
    try:
        repo = CustomerRepository()

        # Get existing customer
        existing = await repo.get_by_id(customer_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Update customer
        update_data = customer_data.dict(exclude_unset=True)
        customer = await repo.update(customer_id, update_data)

        # Trigger AWS profile update
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_updated,
            customer_id=customer_id,
            update_data=update_data
        )

        logger.info("Customer updated", customer_id=customer_id)
        return CustomerResponse.from_orm(customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update customer", customer_id=customer_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer"
        )


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user)
):
    """Delete a customer (soft delete)"""
    try:
        repo = CustomerRepository()

        # Check if customer exists
        customer = await repo.get_by_id(customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Soft delete
        await repo.delete(customer_id)

        # Trigger AWS cleanup
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_deleted,
            customer_id=customer_id
        )

        logger.info("Customer deleted", customer_id=customer_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete customer", customer_id=customer_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer"
        )


@router.post("/{customer_id}/assess-risk")
async def assess_customer_risk(
    customer_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user)
):
    """Trigger risk assessment for a customer"""
    try:
        repo = CustomerRepository()

        # Verify customer exists
        customer = await repo.get_by_id(customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Trigger risk assessment
        intelligence_service = CustomerIntelligenceService()
        background_tasks.add_task(
            intelligence_service.assess_customer_risk,
            customer_id=customer_id,
            force_refresh=True
        )

        return {
            "message": "Risk assessment initiated",
            "customer_id": customer_id,
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to initiate risk assessment", customer_id=customer_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate risk assessment"
        )