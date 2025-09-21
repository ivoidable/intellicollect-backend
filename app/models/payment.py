"""Payment model"""

from sqlalchemy import Column, String, Float, Text, Boolean, Enum, JSON, ForeignKey, Date
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from app.db.base import Base
from app.models.invoice import PaymentMethod


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class Payment(Base):
    """Payment entity model"""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Payment Details
    payment_number = Column(String(100), unique=True, nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)

    # Financial Information
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    payment_date = Column(Date, nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)

    # Transaction Information
    transaction_id = Column(String(255), unique=True, index=True)
    reference_number = Column(String(255))
    confirmation_number = Column(String(255))

    # Status
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    processing_fee = Column(Float, default=0.0)

    # Receipt Processing
    receipt_url = Column(Text)
    receipt_processed = Column(Boolean, default=False)
    receipt_data = Column(JSON)

    # AWS Integration
    aws_payment_id = Column(String(255), unique=True)
    aws_receipt_processing_id = Column(String(255))

    # Metadata
    notes = Column(Text)
    metadata = Column(JSON, default=dict)
    error_message = Column(Text)

    # Relationships
    invoice = relationship("Invoice", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")
    events = relationship("PaymentEvent", back_populates="payment", cascade="all, delete-orphan")