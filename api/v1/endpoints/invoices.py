"""Invoice endpoints"""

from typing import List, Optional
from uuid import UUID
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
import structlog

from app.db.session import get_db
from app.models.invoice import Invoice, InvoiceStatus
from app.models.customer import Customer
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceUpdate,
    InvoiceResponse,
    InvoiceListResponse
)
from app.services.aws.risk_assessment import RiskAssessmentService
from app.services.aws.communication_engine import CommunicationEngine
from app.services.event_processor import EventProcessor
from app.core.security import get_current_user

router = APIRouter()
logger = structlog.get_logger()


@router.get("/", response_model=InvoiceListResponse)
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, le=100),
    status: Optional[InvoiceStatus] = None,
    customer_id: Optional[UUID] = None,
    overdue_only: bool = False,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user=Depends(get_current_user)
):
    """List all invoices with optional filtering"""
    try:
        query = select(Invoice)

        # Apply filters
        filters = []
        if status:
            filters.append(Invoice.status == status)
        if customer_id:
            filters.append(Invoice.customer_id == customer_id)
        if overdue_only:
            filters.append(Invoice.due_date < date.today())
            filters.append(Invoice.status != InvoiceStatus.PAID)
        if date_from:
            filters.append(Invoice.invoice_date >= date_from)
        if date_to:
            filters.append(Invoice.invoice_date <= date_to)

        if filters:
            query = query.where(and_(*filters))

        # Count total
        count_query = select(func.count()).select_from(Invoice)
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and sorting
        query = query.order_by(Invoice.created_at.desc()).offset(skip).limit(limit)

        result = await db.execute(query)
        invoices = result.scalars().all()

        return InvoiceListResponse(
            invoices=[InvoiceResponse.from_orm(i) for i in invoices],
            total=total,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error("Failed to list invoices", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve invoices"
        )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get a specific invoice by ID"""
    query = select(Invoice).where(Invoice.id == invoice_id)
    result = await db.execute(query)
    invoice = result.scalar_one_or_none()

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice {invoice_id} not found"
        )

    return InvoiceResponse.from_orm(invoice)


@router.post("/", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    invoice_data: InvoiceCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new invoice"""
    try:
        # Verify customer exists
        customer_query = select(Customer).where(Customer.id == invoice_data.customer_id)
        customer_result = await db.execute(customer_query)
        customer = customer_result.scalar_one_or_none()

        if not customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer not found"
            )

        # Generate invoice number
        invoice_number = await _generate_invoice_number(db)

        # Calculate totals
        subtotal = sum(item['quantity'] * item['unit_price'] for item in invoice_data.line_items)
        tax_amount = subtotal * (invoice_data.tax_rate / 100) if invoice_data.tax_rate else 0
        total_amount = subtotal + tax_amount - invoice_data.discount_amount

        # Create invoice
        invoice = Invoice(
            **invoice_data.dict(),
            invoice_number=invoice_number,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
            balance_due=total_amount
        )
        db.add(invoice)
        await db.commit()
        await db.refresh(invoice)

        # Trigger AWS processes
        event_processor = EventProcessor()

        # Assess risk
        risk_service = RiskAssessmentService()
        background_tasks.add_task(
            risk_service.assess_invoice_risk,
            invoice_id=str(invoice.id),
            customer_id=str(customer.id),
            amount=total_amount
        )

        # Process invoice creation event
        background_tasks.add_task(
            event_processor.process_invoice_created,
            invoice_id=str(invoice.id),
            invoice_data=invoice_data.dict()
        )

        # Send invoice notification
        if invoice.status == InvoiceStatus.SENT:
            comm_engine = CommunicationEngine()
            background_tasks.add_task(
                comm_engine.send_invoice_notification,
                invoice_id=str(invoice.id),
                customer_id=str(customer.id)
            )

        logger.info("Invoice created", invoice_id=str(invoice.id))
        return InvoiceResponse.from_orm(invoice)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create invoice", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invoice"
        )


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    invoice_data: InvoiceUpdate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update an existing invoice"""
    try:
        # Get existing invoice
        query = select(Invoice).where(Invoice.id == invoice_id)
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )

        # Prevent updates to paid invoices
        if invoice.status == InvoiceStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update paid invoice"
            )

        # Update fields
        update_data = invoice_data.dict(exclude_unset=True)

        # Recalculate totals if line items changed
        if 'line_items' in update_data:
            subtotal = sum(item['quantity'] * item['unit_price'] for item in update_data['line_items'])
            tax_rate = update_data.get('tax_rate', invoice.tax_rate)
            tax_amount = subtotal * (tax_rate / 100) if tax_rate else 0
            discount_amount = update_data.get('discount_amount', invoice.discount_amount)
            total_amount = subtotal + tax_amount - discount_amount

            update_data['subtotal'] = subtotal
            update_data['tax_amount'] = tax_amount
            update_data['total_amount'] = total_amount
            update_data['balance_due'] = total_amount - invoice.amount_paid

        for field, value in update_data.items():
            setattr(invoice, field, value)

        await db.commit()
        await db.refresh(invoice)

        # Trigger status change events
        if 'status' in update_data:
            event_processor = EventProcessor()
            background_tasks.add_task(
                event_processor.process_invoice_status_changed,
                invoice_id=str(invoice.id),
                old_status=str(invoice.status),
                new_status=str(update_data['status'])
            )

        logger.info("Invoice updated", invoice_id=str(invoice.id))
        return InvoiceResponse.from_orm(invoice)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update invoice", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update invoice"
        )


@router.post("/{invoice_id}/send-reminder")
async def send_invoice_reminder(
    invoice_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Send payment reminder for an invoice"""
    try:
        # Get invoice with customer
        query = select(Invoice).where(Invoice.id == invoice_id)
        result = await db.execute(query)
        invoice = result.scalar_one_or_none()

        if not invoice:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Invoice {invoice_id} not found"
            )

        if invoice.status == InvoiceStatus.PAID:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invoice already paid"
            )

        # Send reminder
        comm_engine = CommunicationEngine()
        background_tasks.add_task(
            comm_engine.send_payment_reminder,
            invoice_id=str(invoice.id),
            customer_id=str(invoice.customer_id),
            urgency="normal" if invoice.due_date >= date.today() else "high"
        )

        # Update reminder count
        invoice.reminder_count += 1
        invoice.last_reminder_date = date.today()
        await db.commit()

        return {
            "message": "Payment reminder sent",
            "invoice_id": str(invoice_id),
            "reminder_count": invoice.reminder_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to send reminder", error=str(e))
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send reminder"
        )


async def _generate_invoice_number(db: AsyncSession) -> str:
    """Generate unique invoice number"""
    # Get latest invoice number
    query = select(func.max(Invoice.invoice_number))
    result = await db.execute(query)
    latest = result.scalar()

    if latest:
        # Extract number and increment
        try:
            num = int(latest.split('-')[-1])
            return f"INV-{datetime.now().year}-{num + 1:06d}"
        except:
            pass

    return f"INV-{datetime.now().year}-000001"