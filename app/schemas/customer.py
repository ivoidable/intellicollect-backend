"""Customer schemas for API requests and responses"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class CustomerStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CustomerBase(BaseModel):
    name: str = Field(..., description="Customer name")
    email: str = Field(..., description="Customer email")
    phone: Optional[str] = Field(None, description="Phone number")
    address: Optional[str] = Field(None, description="Customer address")
    company: Optional[str] = Field(None, description="Company name")
    industry: Optional[str] = Field(None, description="Industry")
    status: CustomerStatus = Field(default=CustomerStatus.ACTIVE, description="Customer status")
    risk_level: Optional[RiskLevel] = Field(None, description="Risk level")


class CustomerCreate(CustomerBase):
    """Schema for creating a new customer"""
    pass


class CustomerUpdate(BaseModel):
    """Schema for updating a customer"""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    company: Optional[str] = None
    industry: Optional[str] = None
    status: Optional[CustomerStatus] = None
    risk_level: Optional[RiskLevel] = None


class CustomerResponse(CustomerBase):
    """Schema for customer response"""
    id: str = Field(..., description="Customer ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_date: Optional[str] = Field(None, description="Created date")
    total_invoices: int = Field(default=0, description="Total number of invoices")
    outstanding_amount: float = Field(default=0.0, description="Outstanding amount")
    payment_history: Optional[str] = Field(None, description="Payment history")

    class Config:
        from_attributes = True
        orm_mode = True

    @classmethod
    def from_orm(cls, obj):
        """Create from ORM object or dict"""
        if isinstance(obj, dict):
            return cls(**obj)
        return cls.from_orm(obj)


class CustomerListResponse(BaseModel):
    """Schema for customer list response"""
    customers: List[CustomerResponse]
    total: int
    skip: int
    limit: int