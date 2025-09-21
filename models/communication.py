"""Communication model"""

from sqlalchemy import Column, String, Text, Boolean, Enum, JSON, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum
from datetime import datetime

from db.base import Base


class CommunicationType(str, enum.Enum):
    INVOICE_SENT = "invoice_sent"
    PAYMENT_REMINDER = "payment_reminder"
    PAYMENT_CONFIRMATION = "payment_confirmation"
    OVERDUE_NOTICE = "overdue_notice"
    COLLECTION_NOTICE = "collection_notice"
    THANK_YOU = "thank_you"
    CUSTOM = "custom"


class CommunicationChannel(str, enum.Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    PHONE = "phone"
    LETTER = "letter"


class CommunicationStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class Communication(Base):
    """Communication entity model"""

    __tablename__ = "communications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Communication Details
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), index=True)

    # Communication Type and Channel
    communication_type = Column(Enum(CommunicationType), nullable=False, index=True)
    channel = Column(Enum(CommunicationChannel), nullable=False, index=True)

    # Content
    subject = Column(String(500))
    content = Column(Text, nullable=False)
    template_id = Column(String(255))
    personalization_data = Column(JSON, default=dict)

    # Scheduling
    scheduled_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True), index=True)
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))

    # Status and Tracking
    status = Column(Enum(CommunicationStatus), default=CommunicationStatus.SCHEDULED, index=True)
    delivery_status = Column(JSON)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # Engagement Tracking
    opened = Column(Boolean, default=False)
    clicked_links = Column(JSON, default=list)
    engagement_score = Column(Float)

    # AWS Integration
    aws_message_id = Column(String(255), unique=True)
    aws_campaign_id = Column(String(255))
    aws_personalization_id = Column(String(255))

    # AI Generated Content
    ai_generated = Column(Boolean, default=False)
    ai_model = Column(String(100))
    ai_confidence_score = Column(Float)
    ai_tone = Column(String(50))

    # Metadata
    metadata = Column(JSON, default=dict)
    tags = Column(JSON, default=list)

    # Relationships
    customer = relationship("Customer", back_populates="communications")
    invoice = relationship("Invoice", back_populates="communications")
    responses = relationship("CommunicationResponse", back_populates="communication", cascade="all, delete-orphan")