"""DynamoDB Model Classes

Pydantic models for DynamoDB entities with validation and serialization
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
from decimal import Decimal
from uuid import uuid4
from pydantic import BaseModel, Field, EmailStr, validator
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class CompanyRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InsightType(str, Enum):
    WARNING = "warning"
    OPPORTUNITY = "opportunity"
    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class BaseEntity(BaseModel):
    """Base model for all DynamoDB entities"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def dict_for_dynamodb(self) -> Dict[str, Any]:
        """Convert model to DynamoDB-compatible dict"""
        data = self.dict()
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, date):
                data[key] = value.isoformat()
            elif isinstance(value, Decimal):
                data[key] = str(value)
            elif isinstance(value, Enum):
                data[key] = value.value
        return data

    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            Decimal: lambda v: str(v)
        }


class User(BaseEntity):
    """User model for authentication and profile"""
    email: EmailStr
    password_hash: str
    first_name: str
    last_name: str
    role: UserRole = UserRole.USER
    is_active: bool = True
    email_verified: bool = False
    last_login_at: Optional[datetime] = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Company(BaseEntity):
    """Company/Organization model"""
    name: str
    industry: Optional[str] = None
    company_size: Optional[str] = None
    website: Optional[str] = None
    tax_id: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "USA"
    phone: Optional[str] = None
    billing_email: Optional[EmailStr] = None
    billing_frequency: Optional[str] = None
    preferred_payment_methods: List[str] = Field(default_factory=list)
    logo_url: Optional[str] = None


class UserCompany(BaseEntity):
    """Relationship between users and companies"""
    user_id: str
    company_id: str
    role: CompanyRole = CompanyRole.MEMBER
    joined_at: datetime = Field(default_factory=datetime.utcnow)


class Customer(BaseEntity):
    """Customer model for billing"""
    customer_name: str
    email: EmailStr
    phone: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "USA"
    tax_id: Optional[str] = None
    payment_terms: int = 30  # Days
    credit_limit: Optional[Decimal] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    is_active: bool = True


class InvoiceItem(BaseModel):
    """Line item for invoices"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    quantity: Decimal
    unit_price: Decimal
    discount_percent: Decimal = Decimal("0")
    tax_percent: Decimal = Decimal("0")
    line_total: Decimal = Decimal("0")
    sort_order: int = 0

    @validator("line_total", always=True)
    def calculate_line_total(cls, v, values):
        quantity = values.get("quantity", Decimal("0"))
        unit_price = values.get("unit_price", Decimal("0"))
        discount_percent = values.get("discount_percent", Decimal("0"))
        tax_percent = values.get("tax_percent", Decimal("0"))

        subtotal = quantity * unit_price
        discount = subtotal * (discount_percent / 100)
        after_discount = subtotal - discount
        tax = after_discount * (tax_percent / 100)
        return after_discount + tax


class Invoice(BaseEntity):
    """Invoice model"""
    customer_id: str
    invoice_number: str
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issue_date: date
    due_date: date
    currency: str = "USD"
    subtotal: Decimal
    tax_amount: Decimal = Decimal("0")
    discount_amount: Decimal = Decimal("0")
    total_amount: Decimal
    amount_paid: Decimal = Decimal("0")
    balance_due: Decimal
    payment_terms: Optional[int] = None
    items: List[InvoiceItem] = Field(default_factory=list)
    notes: Optional[str] = None
    terms_conditions: Optional[str] = None
    created_by: Optional[str] = None
    sent_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    @validator("balance_due", always=True)
    def calculate_balance(cls, v, values):
        total = values.get("total_amount", Decimal("0"))
        paid = values.get("amount_paid", Decimal("0"))
        return total - paid


class Payment(BaseEntity):
    """Payment model"""
    customer_id: str
    invoice_id: str
    payment_number: str
    amount: Decimal
    currency: str = "USD"
    payment_date: date
    payment_method: str
    transaction_id: Optional[str] = None
    reference_number: Optional[str] = None
    confirmation_number: Optional[str] = None
    status: str = "completed"
    processing_fee: Decimal = Decimal("0")
    notes: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskAssessment(BaseEntity):
    """AI Risk Assessment model"""
    customer_id: Optional[str] = None
    invoice_id: Optional[str] = None
    risk_level: RiskLevel
    risk_score: Optional[Decimal] = None
    confidence_score: Optional[Decimal] = None
    risk_factors: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations: List[Dict[str, Any]] = Field(default_factory=list)
    assessed_by: str = "ai"
    override_reason: Optional[str] = None


class AIInsight(BaseEntity):
    """AI-generated business insight model"""
    type: InsightType
    category: Optional[str] = None
    title: str
    description: str
    action_required: Optional[str] = None
    priority: Optional[Priority] = None
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None


class Receipt(BaseEntity):
    """Receipt upload model"""
    invoice_id: Optional[str] = None
    file_url: str
    file_name: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    extraction_confidence: Optional[Decimal] = None
    status: str = "pending"
    uploaded_by: Optional[str] = None
    processed_at: Optional[datetime] = None


class AuditLog(BaseEntity):
    """Audit trail model"""
    user_id: Optional[str] = None
    entity_type: str
    entity_id: Optional[str] = None
    action: str  # create, update, delete, view
    changes: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class Setting(BaseEntity):
    """Settings model"""
    key: str
    value: Any
    category: Optional[str] = None


class APIToken(BaseEntity):
    """API token allocation model"""
    token_count: int = 10000
    tokens_used: int = 0
    tokens_remaining: int = 10000
    last_reset_at: datetime = Field(default_factory=datetime.utcnow)
    reset_frequency: str = "monthly"

    @validator("tokens_remaining", always=True)
    def calculate_remaining(cls, v, values):
        total = values.get("token_count", 0)
        used = values.get("tokens_used", 0)
        return total - used


class TokenUsage(BaseEntity):
    """Token usage log model"""
    user_id: Optional[str] = None
    service: str
    tokens_consumed: int
    request_data: Optional[Dict[str, Any]] = None
    response_data: Optional[Dict[str, Any]] = None


class Communication(BaseEntity):
    """Customer communication model"""
    customer_id: str
    invoice_id: Optional[str] = None
    type: str  # email, sms, call
    subject: Optional[str] = None
    content: str
    status: str = "pending"  # pending, sent, delivered, failed
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)