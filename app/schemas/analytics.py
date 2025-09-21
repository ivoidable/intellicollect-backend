"""Analytics schemas for API requests and responses"""

from typing import Optional, List, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, Field


class RevenueMetrics(BaseModel):
    """Revenue metrics"""
    total_revenue: float = Field(..., description="Total revenue")
    outstanding_revenue: float = Field(..., description="Outstanding revenue")
    overdue_revenue: float = Field(..., description="Overdue revenue")
    collected_revenue: float = Field(..., description="Collected revenue")
    average_invoice_value: float = Field(..., description="Average invoice value")
    revenue_growth_rate: float = Field(..., description="Revenue growth rate percentage")


class CustomerMetrics(BaseModel):
    """Customer metrics"""
    total_customers: int = Field(..., description="Total number of customers")
    active_customers: int = Field(..., description="Active customers")
    at_risk_customers: int = Field(..., description="Customers at risk")
    average_payment_delay: float = Field(..., description="Average payment delay in days")
    customer_retention_rate: float = Field(..., description="Customer retention rate percentage")
    churn_rate: float = Field(..., description="Customer churn rate percentage")


class InvoiceMetrics(BaseModel):
    """Invoice metrics"""
    total_invoices: int = Field(..., description="Total number of invoices")
    paid_invoices: int = Field(..., description="Number of paid invoices")
    pending_invoices: int = Field(..., description="Number of pending invoices")
    overdue_invoices: int = Field(..., description="Number of overdue invoices")
    average_days_to_payment: float = Field(..., description="Average days to payment")
    collection_rate: float = Field(..., description="Collection rate percentage")


class RiskMetrics(BaseModel):
    """Risk metrics"""
    average_risk_score: float = Field(..., description="Average risk score")
    high_risk_customers: int = Field(..., description="Number of high-risk customers")
    medium_risk_customers: int = Field(..., description="Number of medium-risk customers")
    low_risk_customers: int = Field(..., description="Number of low-risk customers")
    risk_trend: str = Field(..., description="Overall risk trend")


class DashboardResponse(BaseModel):
    """Dashboard analytics response"""
    period_start: date = Field(..., description="Analytics period start")
    period_end: date = Field(..., description="Analytics period end")
    revenue_metrics: RevenueMetrics = Field(..., description="Revenue metrics")
    customer_metrics: CustomerMetrics = Field(..., description="Customer metrics")
    invoice_metrics: InvoiceMetrics = Field(..., description="Invoice metrics")
    risk_metrics: RiskMetrics = Field(..., description="Risk metrics")
    recent_activities: List[Dict[str, Any]] = Field(..., description="Recent activities")
    generated_at: datetime = Field(..., description="When analytics were generated")


class TrendAnalysis(BaseModel):
    """Trend analysis response"""
    metric_name: str = Field(..., description="Metric name")
    period: str = Field(..., description="Analysis period")
    data_points: List[Dict[str, Any]] = Field(..., description="Time series data points")
    trend: str = Field(..., description="Trend direction")
    forecast: Optional[List[Dict[str, Any]]] = Field(None, description="Forecasted values")


class CustomerAnalytics(BaseModel):
    """Customer-specific analytics"""
    customer_id: str = Field(..., description="Customer ID")
    lifetime_value: float = Field(..., description="Customer lifetime value")
    total_spent: float = Field(..., description="Total amount spent")
    total_invoices: int = Field(..., description="Total number of invoices")
    average_payment_time: float = Field(..., description="Average payment time in days")
    risk_score: float = Field(..., description="Current risk score")
    payment_history: List[Dict[str, Any]] = Field(..., description="Payment history")
    communication_effectiveness: float = Field(..., description="Communication effectiveness score")