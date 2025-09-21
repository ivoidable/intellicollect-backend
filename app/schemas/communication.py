"""Communication schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr
from enum import Enum


class CommunicationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"
    WEBHOOK = "webhook"


class CommunicationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    OPENED = "opened"
    CLICKED = "clicked"


class EmailTemplate(str, Enum):
    INVOICE_CREATED = "invoice_created"
    PAYMENT_REMINDER = "payment_reminder"
    PAYMENT_OVERDUE = "payment_overdue"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_PLAN_CREATED = "payment_plan_created"
    RISK_ALERT = "risk_alert"
    CUSTOM = "custom"


class CommunicationBase(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    communication_type: CommunicationType = Field(..., description="Communication type")
    subject: Optional[str] = Field(None, description="Email subject")
    status: CommunicationStatus = Field(..., description="Communication status")
    tone: Optional[str] = Field(None, description="Communication tone")
    sent_date: Optional[str] = Field(None, description="Date when sent")


class CommunicationCreate(BaseModel):
    """Schema for creating a new communication"""
    customer_id: str = Field(..., description="Customer ID")
    type: CommunicationType = Field(default=CommunicationType.EMAIL)
    recipient_email: EmailStr = Field(..., description="Recipient email")
    template: EmailTemplate = Field(..., description="Email template to use")
    template_data: Dict[str, Any] = Field(..., description="Data for template rendering")
    schedule_at: Optional[datetime] = Field(None, description="Schedule for later sending")


class CommunicationResponse(CommunicationBase):
    """Schema for communication response"""
    communication_id: str = Field(..., description="Communication ID")

    class Config:
        from_attributes = True


class CommunicationHistory(BaseModel):
    """Schema for communication history"""
    customer_id: str = Field(..., description="Customer ID")
    communications: List[CommunicationResponse] = Field(..., description="Communications list")
    total_sent: int = Field(..., description="Total communications sent")
    total_delivered: int = Field(..., description="Total delivered")
    total_opened: int = Field(..., description="Total opened")