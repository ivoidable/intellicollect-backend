"""Risk assessment schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskFactors(BaseModel):
    """Risk assessment factors"""
    payment_history_score: float = Field(..., ge=0, le=100, description="Payment history score")
    outstanding_amount_score: float = Field(..., ge=0, le=100, description="Outstanding amount score")
    overdue_days_score: float = Field(..., ge=0, le=100, description="Overdue days score")
    customer_tenure_score: float = Field(..., ge=0, le=100, description="Customer tenure score")
    payment_frequency_score: float = Field(..., ge=0, le=100, description="Payment frequency score")


class RiskAssessmentBase(BaseModel):
    customer_id: str = Field(..., description="Customer ID")
    invoice_id: Optional[str] = Field(None, description="Invoice ID if assessment is for specific invoice")
    risk_score: float = Field(..., ge=0, le=100, description="Overall risk score")
    risk_level: RiskLevel = Field(..., description="Risk level")
    factors: RiskFactors = Field(..., description="Risk factors breakdown")
    recommendations: List[str] = Field(default=[], description="Risk mitigation recommendations")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class RiskAssessmentCreate(BaseModel):
    """Schema for triggering risk assessment"""
    customer_id: str = Field(..., description="Customer ID")
    invoice_id: Optional[str] = Field(None, description="Invoice ID")
    trigger_communication: bool = Field(True, description="Trigger communication after assessment")


class RiskAssessmentResponse(RiskAssessmentBase):
    """Schema for risk assessment response"""
    assessment_id: str = Field(..., description="Assessment ID")
    created_at: datetime = Field(..., description="Assessment timestamp")
    triggered_by: str = Field(..., description="What triggered the assessment")
    communication_sent: bool = Field(False, description="Whether communication was sent")

    class Config:
        from_attributes = True


class RiskHistory(BaseModel):
    """Schema for risk assessment history"""
    customer_id: str = Field(..., description="Customer ID")
    assessments: List[RiskAssessmentResponse] = Field(..., description="Risk assessments")
    average_score: float = Field(..., description="Average risk score")
    trend: str = Field(..., description="Risk trend (improving/worsening/stable)")

    class Config:
        from_attributes = True