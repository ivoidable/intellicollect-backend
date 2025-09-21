"""Risk assessment endpoints"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
import structlog
import boto3
from botocore.exceptions import ClientError
import uuid
import json

from app.schemas.risk import (
    RiskAssessmentCreate,
    RiskAssessmentResponse,
    RiskHistory,
    RiskLevel,
    RiskFactors
)
from app.core.config import settings
from app.services.aws.event_bridge import EventBridgeService
from app.services.aws.api_gateway import api_gateway_service

router = APIRouter()
logger = structlog.get_logger()

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
lambda_client = boto3.client('lambda', region_name=settings.AWS_REGION)
risk_scores_table = dynamodb.Table(settings.DYNAMODB_RISK_SCORES_TABLE)
customers_table = dynamodb.Table(settings.DYNAMODB_CUSTOMERS_TABLE)
invoices_table = dynamodb.Table(settings.DYNAMODB_INVOICES_TABLE)


@router.post("/assess-ai")
async def assess_risk_with_ai(
    customer_id: str,
    invoice_data: dict,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Assess customer risk using AI via AWS API Gateway"""
    try:
        # Initialize API Gateway service
        await api_gateway_service.initialize()

        # Call AWS API Gateway to assess risk
        response = await api_gateway_service.assess_risk(
            customer_id=customer_id,
            invoice_data=invoice_data
        )

        logger.info(
            "AI risk assessment completed",
            customer_id=customer_id,
            response=response
        )

        return response

    except Exception as e:
        logger.error("Failed to assess risk with AI", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assess", response_model=RiskAssessmentResponse)
async def trigger_risk_assessment(
    assessment: RiskAssessmentCreate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Trigger risk assessment for a customer"""
    try:
        # Generate assessment ID
        assessment_id = f"RISK-{uuid.uuid4().hex[:8].upper()}"

        # Prepare Lambda payload
        payload = {
            'customer_id': assessment.customer_id,
            'invoice_id': assessment.invoice_id,
            'assessment_id': assessment_id,
            'trigger_communication': assessment.trigger_communication
        }

        # Invoke Lambda function asynchronously
        response = lambda_client.invoke(
            FunctionName=settings.RISK_AGENT_FUNCTION,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(payload)
        )

        # Create initial assessment record
        now = datetime.utcnow().isoformat()
        assessment_data = {
            'assessment_id': assessment_id,
            'customer_id': assessment.customer_id,
            'invoice_id': assessment.invoice_id,
            'risk_score': 0,  # Will be updated by Lambda
            'risk_level': RiskLevel.LOW,
            'factors': {},
            'recommendations': [],
            'triggered_by': 'manual',
            'communication_sent': False,
            'created_at': now,
            'status': 'processing'
        }

        risk_scores_table.put_item(Item=assessment_data)

        # Publish assessment triggered event
        background_tasks.add_task(
            publish_risk_assessment_triggered_event,
            assessment_id,
            assessment.customer_id
        )

        return RiskAssessmentResponse(
            assessment_id=assessment_id,
            customer_id=assessment.customer_id,
            invoice_id=assessment.invoice_id,
            risk_score=0,
            risk_level=RiskLevel.LOW,
            factors=RiskFactors(
                payment_history_score=0,
                outstanding_amount_score=0,
                overdue_days_score=0,
                customer_tenure_score=0,
                payment_frequency_score=0
            ),
            recommendations=[],
            metadata={'status': 'processing'},
            created_at=datetime.fromisoformat(now),
            triggered_by='manual',
            communication_sent=False
        )
    except Exception as e:
        logger.error("Failed to trigger risk assessment", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{assessment_id}", response_model=RiskAssessmentResponse)
async def get_risk_assessment(assessment_id: str):
    """Get risk assessment details"""
    try:
        response = risk_scores_table.get_item(Key={'assessment_id': assessment_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Risk assessment not found")

        item = response['Item']

        # Parse factors
        factors = RiskFactors(
            payment_history_score=item.get('factors', {}).get('payment_history_score', 0),
            outstanding_amount_score=item.get('factors', {}).get('outstanding_amount_score', 0),
            overdue_days_score=item.get('factors', {}).get('overdue_days_score', 0),
            customer_tenure_score=item.get('factors', {}).get('customer_tenure_score', 0),
            payment_frequency_score=item.get('factors', {}).get('payment_frequency_score', 0)
        )

        return RiskAssessmentResponse(
            assessment_id=item['assessment_id'],
            customer_id=item['customer_id'],
            invoice_id=item.get('invoice_id'),
            risk_score=float(item['risk_score']),
            risk_level=item['risk_level'],
            factors=factors,
            recommendations=item.get('recommendations', []),
            metadata=item.get('metadata'),
            created_at=datetime.fromisoformat(item['created_at']),
            triggered_by=item.get('triggered_by', 'system'),
            communication_sent=item.get('communication_sent', False)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get risk assessment", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{customer_id}/current", response_model=RiskAssessmentResponse)
async def get_current_risk(customer_id: str):
    """Get current risk assessment for a customer"""
    try:
        # Query for most recent assessment
        response = risk_scores_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )

        items = response.get('Items', [])
        if not items:
            raise HTTPException(status_code=404, detail="No risk assessment found for customer")

        # Sort by created_at and get the most recent
        sorted_items = sorted(items, key=lambda x: x['created_at'], reverse=True)
        latest = sorted_items[0]

        # Parse factors
        factors = RiskFactors(
            payment_history_score=latest.get('factors', {}).get('payment_history_score', 0),
            outstanding_amount_score=latest.get('factors', {}).get('outstanding_amount_score', 0),
            overdue_days_score=latest.get('factors', {}).get('overdue_days_score', 0),
            customer_tenure_score=latest.get('factors', {}).get('customer_tenure_score', 0),
            payment_frequency_score=latest.get('factors', {}).get('payment_frequency_score', 0)
        )

        return RiskAssessmentResponse(
            assessment_id=latest['assessment_id'],
            customer_id=latest['customer_id'],
            invoice_id=latest.get('invoice_id'),
            risk_score=float(latest['risk_score']),
            risk_level=latest['risk_level'],
            factors=factors,
            recommendations=latest.get('recommendations', []),
            metadata=latest.get('metadata'),
            created_at=datetime.fromisoformat(latest['created_at']),
            triggered_by=latest.get('triggered_by', 'system'),
            communication_sent=latest.get('communication_sent', False)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get current risk", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{customer_id}/history", response_model=RiskHistory)
async def get_risk_history(
    customer_id: str,
    limit: int = Query(10, le=100)
):
    """Get risk assessment history for a customer"""
    try:
        # Query all assessments for customer
        response = risk_scores_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )

        items = response.get('Items', [])

        # Sort by created_at
        sorted_items = sorted(items, key=lambda x: x['created_at'], reverse=True)[:limit]

        # Convert to response models
        assessments = []
        total_score = 0
        for item in sorted_items:
            factors = RiskFactors(
                payment_history_score=item.get('factors', {}).get('payment_history_score', 0),
                outstanding_amount_score=item.get('factors', {}).get('outstanding_amount_score', 0),
                overdue_days_score=item.get('factors', {}).get('overdue_days_score', 0),
                customer_tenure_score=item.get('factors', {}).get('customer_tenure_score', 0),
                payment_frequency_score=item.get('factors', {}).get('payment_frequency_score', 0)
            )

            assessment = RiskAssessmentResponse(
                assessment_id=item['assessment_id'],
                customer_id=item['customer_id'],
                invoice_id=item.get('invoice_id'),
                risk_score=float(item['risk_score']),
                risk_level=item['risk_level'],
                factors=factors,
                recommendations=item.get('recommendations', []),
                metadata=item.get('metadata'),
                created_at=datetime.fromisoformat(item['created_at']),
                triggered_by=item.get('triggered_by', 'system'),
                communication_sent=item.get('communication_sent', False)
            )
            assessments.append(assessment)
            total_score += float(item['risk_score'])

        # Calculate trend
        if len(assessments) >= 2:
            recent_score = assessments[0].risk_score
            previous_score = assessments[1].risk_score
            if recent_score > previous_score:
                trend = 'worsening'
            elif recent_score < previous_score:
                trend = 'improving'
            else:
                trend = 'stable'
        else:
            trend = 'stable'

        average_score = total_score / len(assessments) if assessments else 0

        return RiskHistory(
            customer_id=customer_id,
            assessments=assessments,
            average_score=average_score,
            trend=trend
        )
    except Exception as e:
        logger.error("Failed to get risk history", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def publish_risk_assessment_triggered_event(assessment_id: str, customer_id: str):
    """Publish risk assessment triggered event"""
    try:
        event_bridge = EventBridgeService()
        await event_bridge.initialize()

        await event_bridge.publish_event(
            source='billing.risk.triggered',
            detail_type='Risk Assessment Triggered',
            detail={
                'assessment_id': assessment_id,
                'customer_id': customer_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    except Exception as e:
        logger.error(f"Failed to publish risk assessment event: {str(e)}")