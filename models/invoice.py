"""Invoice model"""

from sqlalchemy import Column, String, Integer, Float, Text, Boolean, Enum, JSON, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import date

from app.db.base import Base


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PaymentMethod(str, enum.Enum):
    CREDIT_CARD = "credit_card"
    ACH = "ach"
    WIRE = "wire"
    CHECK = "check"
    CASH = "cash"
    OTHER = "other"


class Invoice(Base):
    """Invoice entity model"""

    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Invoice Details
    invoice_number = Column(String(100), unique=True, nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Dates
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    payment_date = Column(Date)

    # Financial Information
    subtotal = Column(Float, nullable=False)
    tax_rate = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0)
    balance_due = Column(Float, nullable=False)

    # Line Items
    line_items = Column(JSON, nullable=False)  # Array of item objects

    # Payment Information
    payment_terms = Column(Integer)  # Days
    preferred_payment_method = Column(Enum(PaymentMethod))
    payment_instructions = Column(Text)

    # Status and Risk
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.DRAFT, index=True)
    risk_level = Column(String(20))
    risk_score = Column(Float)
    collection_strategy = Column(String(100))

    # Communication
    reminder_count = Column(Integer, default=0)
    last_reminder_date = Column(Date)
    next_reminder_date = Column(Date)

    # AWS Integration
    aws_invoice_id = Column(String(255), unique=True)
    aws_risk_assessment_id = Column(String(255))
    aws_communication_campaign_id = Column(String(255))

    # Metadata
    notes = Column(Text)
    internal_notes = Column(Text)
    metadata = Column(JSON, default=dict)
    tags = Column(JSON, default=list)

    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    payments = relationship("Payment", back_populates="invoice", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="invoice", cascade="all, delete-orphan")
    events = relationship("InvoiceEvent", back_populates="invoice", cascade="all, delete-orphan")