"""Customer model"""

from sqlalchemy import Column, String, Integer, Float, Text, Boolean, Enum, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
import enum

from db.base import Base


class CustomerStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Customer(Base):
    """Customer entity model"""

    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic Information
    company_name = Column(String(255), nullable=False, index=True)
    contact_name = Column(String(255))
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(50))

    # Address Information
    billing_address = Column(JSON)
    shipping_address = Column(JSON)

    # Business Information
    industry = Column(String(100))
    company_size = Column(String(50))
    tax_id = Column(String(100))

    # Financial Information
    credit_limit = Column(Float, default=0.0)
    payment_terms = Column(Integer, default=30)  # Days
    discount_percentage = Column(Float, default=0.0)

    # Risk Assessment
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW, index=True)
    risk_score = Column(Float, default=0.0)
    risk_factors = Column(JSON, default=list)
    last_risk_assessment = Column(String)  # DateTime as string for simplicity

    # Communication Preferences
    preferred_communication_channel = Column(String(50), default="email")
    communication_preferences = Column(JSON, default=dict)
    unsubscribed = Column(Boolean, default=False)

    # AWS Integration
    aws_customer_profile_id = Column(String(255), unique=True)
    aws_risk_assessment_id = Column(String(255))

    # Status and Metadata
    status = Column(Enum(CustomerStatus), default=CustomerStatus.ACTIVE, index=True)
    metadata = Column(JSON, default=dict)

    # Relationships
    invoices = relationship("Invoice", back_populates="customer", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="customer", cascade="all, delete-orphan")
    communications = relationship("Communication", back_populates="customer", cascade="all, delete-orphan")
    risk_assessments = relationship("RiskAssessment", back_populates="customer", cascade="all, delete-orphan")