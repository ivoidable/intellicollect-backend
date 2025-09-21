"""Customer endpoints"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import structlog

from app.db.session import get_db
from app.models.customer import Customer, CustomerStatus, RiskLevel
from app.schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    CustomerListResponse
)
from app.services.aws.customer_intelligence import CustomerIntelligenceService
from app.services.event_processor import EventProcessor
from app.core.security import get_current_user

router = APIRouter()
logger = structlog.get_logger()


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    status: Optional[CustomerStatus] = None,
    risk_level: Optional[RiskLevel] = None,
    search: Optional[str] = None,
    current_user=Depends(get_current_user)
):
    """List all customers with optional filtering"""
    try:
        query = select(Customer)

        # Apply filters
        filters = []
        if status:
            filters.append(Customer.status == status)
        if risk_level:
            filters.append(Customer.risk_level == risk_level)
        if search:
            filters.append(
                or_(
                    Customer.company_name.ilike(f"%{search}%"),
                    Customer.email.ilike(f"%{search}%"),
                    Customer.contact_name.ilike(f"%{search}%")
                )
            )

        if filters:
            query = query.where(and_(*filters))

        # Count total
        count_query = select(func.count()).select_from(Customer)
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        customers = result.scalars().all()

        return CustomerListResponse(
            customers=[CustomerResponse.from_orm(c) for c in customers],
            total=total,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error("Failed to list customers", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customers"
        )


@router.get("/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get a specific customer by ID"""
    query = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(query)
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found"
        )

    return CustomerResponse.from_orm(customer)


@router.post("/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: CustomerCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new customer"""
    try:
        # Check if email already exists
        existing = await db.execute(
            select(Customer).where(Customer.email == customer_data.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer with this email already exists"
            )

        # Create customer
        customer = Customer(**customer_data.dict())
        db.add(customer)
        await db.commit()
        await db.refresh(customer)

        # Trigger AWS customer profile creation
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_created,
            customer_id=str(customer.id),
            customer_data=customer_data.dict()
        )

        # Trigger initial risk assessment
        intelligence_service = CustomerIntelligenceService()
        background_tasks.add_task(
            intelligence_service.assess_customer_risk,
            customer_id=str(customer.id)
        )

        logger.info("Customer created", customer_id=str(customer.id))
        return CustomerResponse.from_orm(customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create customer", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer"
        )


@router.put("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID,
    customer_data: CustomerUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update an existing customer"""
    try:
        # Get existing customer
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalar_one_or_none()

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Update fields
        update_data = customer_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(customer, field, value)

        await db.commit()
        await db.refresh(customer)

        # Trigger AWS profile update
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_updated,
            customer_id=str(customer.id),
            update_data=update_data
        )

        logger.info("Customer updated", customer_id=str(customer.id))
        return CustomerResponse.from_orm(customer)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update customer", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer"
        )


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete a customer (soft delete)"""
    try:
        # Get existing customer
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalar_one_or_none()

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Soft delete
        customer.status = CustomerStatus.DELETED
        await db.commit()

        # Trigger AWS cleanup
        event_processor = EventProcessor()
        background_tasks.add_task(
            event_processor.process_customer_deleted,
            customer_id=str(customer.id)
        )

        logger.info("Customer deleted", customer_id=str(customer.id))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete customer", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer"
        )


@router.post("/{customer_id}/assess-risk", response_model=dict)
async def assess_customer_risk(
    customer_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Trigger risk assessment for a customer"""
    try:
        # Verify customer exists
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        customer = result.scalar_one_or_none()

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found"
            )

        # Trigger risk assessment
        intelligence_service = CustomerIntelligenceService()
        background_tasks.add_task(
            intelligence_service.assess_customer_risk,
            customer_id=str(customer.id),
            force_refresh=True
        )

        return {
            "message": "Risk assessment initiated",
            "customer_id": str(customer_id),
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to initiate risk assessment", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate risk assessment"
        )