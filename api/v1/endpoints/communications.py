"""Communications endpoints"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Query, BackgroundTasks
import structlog
import boto3
from botocore.exceptions import ClientError
import uuid
import json

from app.schemas.communication import (
    CommunicationCreate,
    CommunicationResponse,
    CommunicationHistory,
    CommunicationStatus,
    CommunicationType,
    EmailTemplate
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
ses_client = boto3.client('ses', region_name=settings.AWS_REGION)
lambda_client = boto3.client('lambda', region_name=settings.AWS_REGION)
communications_table = dynamodb.Table(settings.DYNAMODB_COMMUNICATIONS_TABLE)


@router.post("/send", response_model=CommunicationResponse)
async def send_communication(
    communication: CommunicationCreate,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Send a communication to a customer"""
    try:
        # Generate communication ID
        communication_id = f"COMM-{uuid.uuid4().hex[:8].upper()}"

        # Prepare template data
        email_content = render_email_template(
            communication.template,
            communication.template_data
        )

        # Send email via SES or Lambda
        if communication.schedule_at:
            # Schedule for later via Lambda
            schedule_communication_lambda(
                communication_id,
                communication,
                email_content,
                communication.schedule_at
            )
            status = CommunicationStatus.PENDING
        else:
            # Send immediately via SES
            response = ses_client.send_email(
                Source=settings.VERIFIED_EMAIL,
                Destination={'ToAddresses': [communication.recipient_email]},
                Message={
                    'Subject': {'Data': get_email_subject(communication.template)},
                    'Body': {'Html': {'Data': email_content}}
                }
            )
            status = CommunicationStatus.SENT

        # Save communication record
        now = datetime.utcnow().isoformat()
        communication_data = {
            'communication_id': communication_id,
            'customer_id': communication.customer_id,
            'communication_type': communication.type,
            'subject': get_email_subject(communication.template),
            'status': status,
            'tone': 'professional',
            'sent_date': now[:10] if status == CommunicationStatus.SENT else None
        }

        communications_table.put_item(Item=communication_data)

        return CommunicationResponse(
            communication_id=communication_id,
            customer_id=communication.customer_id,
            communication_type=communication.type,
            subject=get_email_subject(communication.template),
            status=status,
            tone='professional',
            sent_date=now[:10] if status == CommunicationStatus.SENT else None
        )
    except Exception as e:
        logger.error("Failed to send communication", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{communication_id}", response_model=CommunicationResponse)
async def get_communication(communication_id: str):
    """Get communication details"""
    try:
        response = communications_table.get_item(Key={'communication_id': communication_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Communication not found")

        item = response['Item']

        return CommunicationResponse(
            communication_id=item['communication_id'],
            customer_id=item['customer_id'],
            communication_type=item.get('communication_type', 'email'),
            subject=item.get('subject'),
            status=item['status'],
            tone=item.get('tone'),
            sent_date=item.get('sent_date')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get communication", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer/{customer_id}/history", response_model=CommunicationHistory)
async def get_communication_history(
    customer_id: str,
    limit: int = Query(20, le=100)
):
    """Get communication history for a customer"""
    try:
        # Query communications for customer
        response = communications_table.scan(
            FilterExpression="customer_id = :customer_id",
            ExpressionAttributeValues={":customer_id": customer_id}
        )

        items = response.get('Items', [])

        # Sort by created_at
        sorted_items = sorted(items, key=lambda x: x['created_at'], reverse=True)[:limit]

        # Convert to response models
        communications = []
        total_sent = 0
        total_delivered = 0
        total_opened = 0

        for item in sorted_items:
            comm = CommunicationResponse(
                communication_id=item['communication_id'],
                customer_id=item['customer_id'],
                communication_type=item.get('communication_type', 'email'),
                subject=item.get('subject'),
                status=item['status'],
                tone=item.get('tone'),
                sent_date=item.get('sent_date')
            )
            communications.append(comm)

            if item['status'] in [CommunicationStatus.SENT, CommunicationStatus.DELIVERED, CommunicationStatus.OPENED]:
                total_sent += 1
            if item['status'] in [CommunicationStatus.DELIVERED, CommunicationStatus.OPENED]:
                total_delivered += 1
            if item['status'] == CommunicationStatus.OPENED:
                total_opened += 1

        return CommunicationHistory(
            customer_id=customer_id,
            communications=communications,
            total_sent=total_sent,
            total_delivered=total_delivered,
            total_opened=total_opened
        )
    except Exception as e:
        logger.error("Failed to get communication history", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-email")
async def send_test_email(
    recipient_email: str = Query(..., description="Recipient email address"),
    template: EmailTemplate = Query(EmailTemplate.PAYMENT_REMINDER)
):
    """Send a test email"""
    try:
        # Prepare test data
        test_data = {
            'customer_name': 'Test Customer',
            'invoice_number': 'INV-TEST-001',
            'amount': 1000.00,
            'due_date': '2024-12-31',
            'company_name': 'Billing System'
        }

        email_content = render_email_template(template, test_data)

        # Send via SES
        response = ses_client.send_email(
            Source=settings.VERIFIED_EMAIL,
            Destination={'ToAddresses': [recipient_email]},
            Message={
                'Subject': {'Data': f"[TEST] {get_email_subject(template)}"},
                'Body': {'Html': {'Data': email_content}}
            }
        )

        return {
            'message': 'Test email sent successfully',
            'message_id': response['MessageId'],
            'recipient': recipient_email
        }
    except Exception as e:
        logger.error("Failed to send test email", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


def render_email_template(template: EmailTemplate, data: dict) -> str:
    """Render email template with data"""
    templates = {
        EmailTemplate.INVOICE_CREATED: """
            <html>
            <body>
                <h2>New Invoice Created</h2>
                <p>Dear {customer_name},</p>
                <p>A new invoice #{invoice_number} has been created for ${amount:.2f}.</p>
                <p>Due date: {due_date}</p>
                <p>Thank you,<br>{company_name}</p>
            </body>
            </html>
        """,
        EmailTemplate.PAYMENT_REMINDER: """
            <html>
            <body>
                <h2>Payment Reminder</h2>
                <p>Dear {customer_name},</p>
                <p>This is a reminder that invoice #{invoice_number} for ${amount:.2f} is due on {due_date}.</p>
                <p>Please make your payment at your earliest convenience.</p>
                <p>Thank you,<br>{company_name}</p>
            </body>
            </html>
        """,
        EmailTemplate.PAYMENT_OVERDUE: """
            <html>
            <body>
                <h2>Payment Overdue Notice</h2>
                <p>Dear {customer_name},</p>
                <p>Invoice #{invoice_number} for ${amount:.2f} is now overdue.</p>
                <p>Original due date: {due_date}</p>
                <p>Please contact us to arrange payment immediately.</p>
                <p>Thank you,<br>{company_name}</p>
            </body>
            </html>
        """,
        EmailTemplate.PAYMENT_RECEIVED: """
            <html>
            <body>
                <h2>Payment Received</h2>
                <p>Dear {customer_name},</p>
                <p>We have received your payment for invoice #{invoice_number}.</p>
                <p>Amount received: ${amount:.2f}</p>
                <p>Thank you for your prompt payment!</p>
                <p>Best regards,<br>{company_name}</p>
            </body>
            </html>
        """
    }

    template_html = templates.get(template, templates[EmailTemplate.CUSTOM])

    # Format the template with data
    try:
        return template_html.format(**data)
    except KeyError as e:
        logger.warning(f"Missing template variable: {e}")
        return template_html


def get_email_subject(template: EmailTemplate) -> str:
    """Get email subject for template"""
    subjects = {
        EmailTemplate.INVOICE_CREATED: "New Invoice Created",
        EmailTemplate.PAYMENT_REMINDER: "Payment Reminder",
        EmailTemplate.PAYMENT_OVERDUE: "Payment Overdue Notice",
        EmailTemplate.PAYMENT_RECEIVED: "Payment Received",
        EmailTemplate.PAYMENT_PLAN_CREATED: "Payment Plan Created",
        EmailTemplate.RISK_ALERT: "Account Risk Alert",
        EmailTemplate.CUSTOM: "Important Notice"
    }
    return subjects.get(template, "Billing Notification")


def schedule_communication_lambda(communication_id: str, communication: CommunicationCreate, content: str, schedule_at: datetime):
    """Schedule communication via Lambda"""
    try:
        payload = {
            'communication_id': communication_id,
            'customer_id': communication.customer_id,
            'recipient_email': communication.recipient_email,
            'subject': get_email_subject(communication.template),
            'content': content,
            'schedule_at': schedule_at.isoformat()
        }

        lambda_client.invoke(
            FunctionName=settings.COMMUNICATION_AGENT_FUNCTION,
            InvocationType='Event',
            Payload=json.dumps(payload)
        )
    except Exception as e:
        logger.error(f"Failed to schedule communication: {str(e)}")