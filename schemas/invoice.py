"""Invoice schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field
from enum import Enum


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    REFUNDED = "refunded"


class InvoiceItem(BaseModel):
    description: str = Field(..., description="Item description")
    quantity: int = Field(..., ge=1, description="Item quantity")
    unit_price: float = Field(..., ge=0, description="Unit price")
    total: float = Field(..., ge=0, description="Total price")
    tax_rate: Optional[float] = Field(0.0, ge=0, le=100, description="Tax rate percentage")


class InvoiceBase(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    invoice_date: date = Field(..., description="Invoice date")
    due_date: date = Field(..., description="Invoice due date")
    amount: float = Field(..., ge=0, description="Invoice amount")
    total_amount: float = Field(..., ge=0, description="Total amount")
    currency: str = Field("USD", description="Currency code")
    status: InvoiceStatus = Field(default=InvoiceStatus.DRAFT, description="Invoice status")
    payment_status: PaymentStatus = Field(default=PaymentStatus.UNPAID, description="Payment status")
    risk_level: Optional[str] = Field(None, description="Risk level")
    risk_score: Optional[float] = Field(None, description="Risk score")


class InvoiceCreate(InvoiceBase):
    """Schema for creating a new invoice"""
    pass


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice"""
    customer_id: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[InvoiceStatus] = None
    payment_status: Optional[PaymentStatus] = None
    risk_level: Optional[str] = None
    risk_score: Optional[float] = None


class InvoiceResponse(InvoiceBase):
    """Schema for invoice response"""
    invoice_id: str = Field(..., description="Invoice ID")
    created_timestamp: Optional[str] = Field(None, description="Creation timestamp")
    paid_amount: float = Field(0.0, description="Amount paid")
    outstanding_amount: float = Field(0.0, description="Outstanding amount")
    reminder_count: Optional[int] = Field(0, description="Reminder count")
    last_reminder_date: Optional[str] = Field(None, description="Last reminder date")
    payment_date: Optional[str] = Field(None, description="Payment date")
    payment_reference: Optional[str] = Field(None, description="Payment reference")

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Schema for invoice list response"""
    invoices: List[InvoiceResponse]
    total: int
    skip: int
    limit: int