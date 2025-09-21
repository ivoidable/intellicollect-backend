"""Payment schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class PaymentMethod(str, Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    CHECK = "check"
    CASH = "cash"
    PAYPAL = "paypal"
    STRIPE = "stripe"
    OTHER = "other"


class TransactionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentPlanStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    OVERDUE = "overdue"


class PaymentBase(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    amount: float = Field(..., ge=0, description="Payment amount")
    currency: str = Field("USD", description="Currency code")
    transaction_date: str = Field(..., description="Transaction date")
    reference_number: Optional[str] = Field(None, description="Payment reference number")
    status: TransactionStatus = Field(default=TransactionStatus.PENDING, description="Transaction status")
    transaction_type: Optional[str] = Field(None, description="Transaction type")
    processing_method: Optional[str] = Field(None, description="Processing method")
    bank_name: Optional[str] = Field(None, description="Bank name")
    payer_name: Optional[str] = Field(None, description="Payer name")
    fees: Optional[float] = Field(0.0, description="Transaction fees")


class PaymentCreate(PaymentBase):
    """Schema for creating a new payment"""
    receipt_image_key: Optional[str] = Field(None, description="Receipt image S3 key")


class PaymentResponse(PaymentBase):
    """Schema for payment response"""
    transaction_id: str = Field(..., description="Transaction ID")
    processed_date: Optional[str] = Field(None, description="Processing date")
    receipt_image_key: Optional[str] = Field(None, description="Receipt image S3 key")
    confidence_score: Optional[float] = Field(None, description="AI confidence score")

    class Config:
        from_attributes = True


class PaymentPlan(BaseModel):
    """Schema for payment plans"""
    plan_id: Optional[str] = Field(None, description="Payment plan ID")
    customer_id: str = Field(..., description="Customer ID")
    invoice_id: str = Field(..., description="Invoice ID")
    total_amount: float = Field(..., ge=0, description="Total amount")
    installments: int = Field(..., ge=2, description="Number of installments")
    installment_amount: float = Field(..., ge=0, description="Amount per installment")
    frequency: str = Field("monthly", description="Payment frequency")
    start_date: datetime = Field(..., description="Plan start date")
    end_date: datetime = Field(..., description="Plan end date")
    status: PaymentPlanStatus = Field(default=PaymentPlanStatus.ACTIVE, description="Plan status")
    paid_installments: int = Field(0, ge=0, description="Number of paid installments")
    next_payment_date: Optional[datetime] = Field(None, description="Next payment due date")

    class Config:
        from_attributes = True


class ReceiptUploadResponse(BaseModel):
    """Schema for receipt upload response"""
    file_name: str = Field(..., description="Uploaded file name")
    s3_key: str = Field(..., description="S3 object key")
    bucket_name: str = Field(..., description="S3 bucket name")
    upload_url: Optional[str] = Field(None, description="Presigned URL for access")
    uploaded_at: datetime = Field(..., description="Upload timestamp")
    size: int = Field(..., description="File size in bytes")
    content_type: str = Field(..., description="File content type")