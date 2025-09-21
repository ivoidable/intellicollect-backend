"""Analytics and dashboard endpoints"""

from typing import List, Dict, Any
from datetime import datetime, date, timedelta
from fastapi import APIRouter, HTTPException, status, Query
import structlog
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal

from app.schemas.analytics import (
    DashboardResponse,
    RevenueMetrics,
    CustomerMetrics,
    InvoiceMetrics,
    RiskMetrics,
    TrendAnalysis,
    CustomerAnalytics
)
from app.core.config import settings

router = APIRouter()
logger = structlog.get_logger()

# Initialize AWS clients
import os
if settings.AWS_ACCESS_KEY_ID:
    os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
if settings.AWS_SECRET_ACCESS_KEY:
    os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
if settings.AWS_REGION:
    os.environ['AWS_DEFAULT_REGION'] = settings.AWS_REGION

dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
invoices_table = dynamodb.Table(settings.DYNAMODB_INVOICES_TABLE)
customers_table = dynamodb.Table(settings.DYNAMODB_CUSTOMERS_TABLE)
payments_table = dynamodb.Table(settings.DYNAMODB_PAYMENT_RECORDS_TABLE)
risk_scores_table = dynamodb.Table(settings.DYNAMODB_RISK_SCORES_TABLE)
communications_table = dynamodb.Table(settings.DYNAMODB_COMMUNICATIONS_TABLE)


@router.get("/summary")
async def get_summary_stats():
    """Get quick summary statistics for the dashboard"""
    try:
        # Get quick counts from each table
        customers = customers_table.scan()['Items']
        invoices = invoices_table.scan()['Items']
        payments = payments_table.scan()['Items']

        return {
            "total_customers": len(customers),
            "total_invoices": len(invoices),
            "total_payments": len(payments),
            "total_revenue": sum(float(inv.get('total_amount', 0)) for inv in invoices),
            "pending_invoices": len([inv for inv in invoices if inv.get('payment_status') == 'unpaid']),
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Failed to get summary stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_analytics(
    period_days: int = Query(30, description="Number of days to analyze")
):
    """Get comprehensive dashboard analytics"""
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Get all data
        invoices = invoices_table.scan()['Items']
        customers = customers_table.scan()['Items']
        payments = payments_table.scan()['Items']
        risk_scores = risk_scores_table.scan()['Items']

        # Calculate revenue metrics
        revenue_metrics = calculate_revenue_metrics(invoices, start_date, end_date)

        # Calculate customer metrics
        customer_metrics = calculate_customer_metrics(customers, invoices)

        # Calculate invoice metrics
        invoice_metrics = calculate_invoice_metrics(invoices, payments)

        # Calculate risk metrics
        risk_metrics = calculate_risk_metrics(risk_scores, customers)

        # Get recent activities
        recent_activities = get_recent_activities(invoices, payments, communications_table)

        return DashboardResponse(
            period_start=start_date,
            period_end=end_date,
            revenue_metrics=revenue_metrics,
            customer_metrics=customer_metrics,
            invoice_metrics=invoice_metrics,
            risk_metrics=risk_metrics,
            recent_activities=recent_activities,
            generated_at=datetime.utcnow()
        )
    except Exception as e:
        logger.error("Failed to generate dashboard analytics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/revenue/trend", response_model=TrendAnalysis)
async def get_revenue_trend(
    period: str = Query("monthly", description="Period: daily, weekly, monthly"),
    months: int = Query(6, description="Number of months to analyze")
):
    """Get revenue trend analysis"""
    try:
        invoices = invoices_table.scan()['Items']
        payments = payments_table.scan()['Items']

        # Generate data points based on period
        data_points = []
        if period == "monthly":
            for i in range(months):
                month_start = date.today().replace(day=1) - timedelta(days=30 * i)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)

                month_revenue = sum(
                    float(inv.get('total_amount', 0))
                    for inv in invoices
                    if month_start <= date.fromisoformat(inv.get('invoice_date', inv.get('created_timestamp', datetime.utcnow().isoformat())[:10])) <= month_end
                )

                data_points.append({
                    'period': month_start.strftime('%Y-%m'),
                    'revenue': month_revenue,
                    'invoices': len([i for i in invoices if month_start <= date.fromisoformat(i.get('invoice_date', i.get('created_timestamp', datetime.utcnow().isoformat())[:10])) <= month_end])
                })

        # Calculate trend
        if len(data_points) >= 2:
            recent_revenue = data_points[0]['revenue']
            previous_revenue = data_points[1]['revenue']
            trend = "increasing" if recent_revenue > previous_revenue else "decreasing" if recent_revenue < previous_revenue else "stable"
        else:
            trend = "stable"

        return TrendAnalysis(
            metric_name="revenue",
            period=period,
            data_points=data_points,
            trend=trend,
            forecast=None  # Could implement forecasting here
        )
    except Exception as e:
        logger.error("Failed to generate revenue trend", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{customer_id}/analytics", response_model=CustomerAnalytics)
async def get_customer_analytics(customer_id: str):
    """Get detailed analytics for a specific customer"""
    try:
        # Get customer data
        customer_response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in customer_response:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Get customer invoices
        invoices_response = invoices_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )
        invoices = invoices_response['Items']

        # Get customer payments
        payments_response = payments_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )
        payments = payments_response['Items']

        # Get latest risk score
        risk_response = risk_scores_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )
        risk_scores = risk_response['Items']
        latest_risk = sorted(risk_scores, key=lambda x: x['created_at'], reverse=True)[0] if risk_scores else None

        # Calculate metrics
        total_spent = sum(float(p.get('amount', 0)) for p in payments)
        total_invoices = len(invoices)

        # Calculate average payment time
        payment_times = []
        for invoice in invoices:
            if invoice.get('payment_status') == 'paid':
                invoice_date = date.fromisoformat(invoice['issue_date'])
                # Find corresponding payment
                invoice_payments = [p for p in payments if p['invoice_id'] == invoice['invoice_id']]
                if invoice_payments:
                    payment_date = date.fromisoformat(invoice_payments[0]['payment_date'].split('T')[0])
                    days = (payment_date - invoice_date).days
                    payment_times.append(days)

        avg_payment_time = sum(payment_times) / len(payment_times) if payment_times else 0

        # Get payment history
        payment_history = [
            {
                'date': p['payment_date'],
                'amount': float(p['amount']),
                'invoice_id': p['invoice_id'],
                'status': p.get('status', 'success')
            }
            for p in sorted(payments, key=lambda x: x['payment_date'], reverse=True)[:10]
        ]

        # Calculate communication effectiveness (simplified)
        comm_response = communications_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )
        communications = comm_response['Items']
        opened_comms = len([c for c in communications if c.get('status') == 'opened'])
        total_comms = len(communications)
        comm_effectiveness = (opened_comms / total_comms * 100) if total_comms > 0 else 0

        return CustomerAnalytics(
            customer_id=customer_id,
            lifetime_value=total_spent,
            total_spent=total_spent,
            total_invoices=total_invoices,
            average_payment_time=avg_payment_time,
            risk_score=float(latest_risk['risk_score']) if latest_risk else 0,
            payment_history=payment_history,
            communication_effectiveness=comm_effectiveness
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get customer analytics", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def calculate_revenue_metrics(invoices: List[Dict], start_date: date, end_date: date) -> RevenueMetrics:
    """Calculate revenue metrics"""
    period_invoices = [
        inv for inv in invoices
        if start_date <= date.fromisoformat(inv.get('invoice_date', inv.get('created_timestamp', datetime.utcnow().isoformat())[:10])) <= end_date
    ]

    total_revenue = sum(float(inv.get('total_amount', 0)) for inv in period_invoices)
    outstanding_revenue = sum(float(inv.get('outstanding_amount', 0)) for inv in period_invoices)
    collected_revenue = total_revenue - outstanding_revenue

    overdue_invoices = [
        inv for inv in period_invoices
        if date.fromisoformat(inv['due_date']) < date.today() and inv.get('payment_status') != 'paid'
    ]
    overdue_revenue = sum(float(inv.get('outstanding_amount', 0)) for inv in overdue_invoices)

    avg_invoice = total_revenue / len(period_invoices) if period_invoices else 0

    # Calculate growth rate (simplified - compare to previous period)
    prev_start = start_date - (end_date - start_date)
    prev_end = start_date
    prev_invoices = [
        inv for inv in invoices
        if prev_start <= date.fromisoformat(inv.get('invoice_date', inv.get('created_timestamp', datetime.utcnow().isoformat())[:10])) < prev_end
    ]
    prev_revenue = sum(float(inv.get('total_amount', 0)) for inv in prev_invoices)
    growth_rate = ((total_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0

    return RevenueMetrics(
        total_revenue=total_revenue,
        outstanding_revenue=outstanding_revenue,
        overdue_revenue=overdue_revenue,
        collected_revenue=collected_revenue,
        average_invoice_value=avg_invoice,
        revenue_growth_rate=growth_rate
    )


def calculate_customer_metrics(customers: List[Dict], invoices: List[Dict]) -> CustomerMetrics:
    """Calculate customer metrics"""
    total_customers = len(customers)
    active_customers = len(set(inv['customer_id'] for inv in invoices if inv.get('status') != 'cancelled'))

    # Calculate at-risk customers (simplified - those with overdue invoices)
    overdue_customer_ids = set(
        inv['customer_id'] for inv in invoices
        if date.fromisoformat(inv['due_date']) < date.today() and inv.get('payment_status') != 'paid'
    )
    at_risk_customers = len(overdue_customer_ids)

    # Calculate average payment delay
    delays = []
    for inv in invoices:
        if inv.get('payment_status') == 'paid':
            due = date.fromisoformat(inv['due_date'])
            # Simplified - would need actual payment date
            delays.append(0)  # Placeholder

    avg_delay = sum(delays) / len(delays) if delays else 0

    # Simplified retention and churn rates
    retention_rate = 85.0  # Placeholder
    churn_rate = 15.0  # Placeholder

    return CustomerMetrics(
        total_customers=total_customers,
        active_customers=active_customers,
        at_risk_customers=at_risk_customers,
        average_payment_delay=avg_delay,
        customer_retention_rate=retention_rate,
        churn_rate=churn_rate
    )


def calculate_invoice_metrics(invoices: List[Dict], payments: List[Dict]) -> InvoiceMetrics:
    """Calculate invoice metrics"""
    total_invoices = len(invoices)
    paid_invoices = len([inv for inv in invoices if inv.get('payment_status') == 'paid'])
    pending_invoices = len([inv for inv in invoices if inv.get('payment_status') == 'unpaid'])
    overdue_invoices = len([
        inv for inv in invoices
        if date.fromisoformat(inv['due_date']) < date.today() and inv.get('payment_status') != 'paid'
    ])

    # Calculate average days to payment (simplified)
    avg_days = 15  # Placeholder

    collection_rate = (paid_invoices / total_invoices * 100) if total_invoices > 0 else 0

    return InvoiceMetrics(
        total_invoices=total_invoices,
        paid_invoices=paid_invoices,
        pending_invoices=pending_invoices,
        overdue_invoices=overdue_invoices,
        average_days_to_payment=avg_days,
        collection_rate=collection_rate
    )


def calculate_risk_metrics(risk_scores: List[Dict], customers: List[Dict]) -> RiskMetrics:
    """Calculate risk metrics"""
    if not risk_scores:
        return RiskMetrics(
            average_risk_score=0,
            high_risk_customers=0,
            medium_risk_customers=0,
            low_risk_customers=0,
            risk_trend="stable"
        )

    # Get latest risk score for each customer
    customer_risks = {}
    for score in risk_scores:
        cust_id = score['customer_id']
        if cust_id not in customer_risks or score['created_at'] > customer_risks[cust_id]['created_at']:
            customer_risks[cust_id] = score

    scores = [float(r['risk_score']) for r in customer_risks.values()]
    avg_score = sum(scores) / len(scores) if scores else 0

    high_risk = len([s for s in scores if s > 70])
    medium_risk = len([s for s in scores if 30 <= s <= 70])
    low_risk = len([s for s in scores if s < 30])

    # Determine trend (simplified)
    risk_trend = "stable"

    return RiskMetrics(
        average_risk_score=avg_score,
        high_risk_customers=high_risk,
        medium_risk_customers=medium_risk,
        low_risk_customers=low_risk,
        risk_trend=risk_trend
    )


def get_recent_activities(invoices: List[Dict], payments: List[Dict], communications_table) -> List[Dict[str, Any]]:
    """Get recent activities"""
    activities = []

    # Recent invoices
    recent_invoices = sorted(invoices, key=lambda x: x.get('created_timestamp', x.get('created_at', datetime.utcnow().isoformat())), reverse=True)[:5]
    for inv in recent_invoices:
        activities.append({
            'type': 'invoice_created',
            'description': f"Invoice {inv['invoice_id']} created",
            'amount': float(inv.get('total_amount', 0)),
            'timestamp': inv.get('created_timestamp', inv.get('created_at', datetime.utcnow().isoformat()))
        })

    # Recent payments
    recent_payments = sorted(payments, key=lambda x: x.get('processed_date', x.get('transaction_date', datetime.utcnow().isoformat())), reverse=True)[:5]
    for pay in recent_payments:
        activities.append({
            'type': 'payment_received',
            'description': f"Payment received from {pay.get('payer_name', 'Customer')}",
            'amount': float(pay.get('amount', 0)),
            'timestamp': pay.get('processed_date', pay.get('transaction_date', datetime.utcnow().isoformat()))
        })

    # Sort all activities by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)

    return activities[:10]  # Return top 10 most recent