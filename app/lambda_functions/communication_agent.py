"""Communication Agent Lambda Function

Handles all customer email communications with AI-personalized messaging
"""

import json
import boto3
import os
from datetime import datetime
from decimal import Decimal
import logging
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ses = boto3.client('ses', region_name='ap-southeast-1')
dynamodb = boto3.resource('dynamodb')
bedrock = boto3.client('bedrock-runtime', region_name='ap-southeast-1')

# DynamoDB tables
customers_table = dynamodb.Table('BillingCustomers')
invoices_table = dynamodb.Table('BillingInvoices')
communications_table = dynamodb.Table('Communications')

# Configuration
VERIFIED_EMAIL = os.environ.get('VERIFIED_EMAIL', 'billing@yourcompany.com')
COMPANY_NAME = os.environ.get('COMPANY_NAME', 'YourCompany')


def lambda_handler(event, context):
    """Main Lambda handler for communication agent"""
    logger.info(f"Communication Agent triggered with event: {json.dumps(event)}")

    try:
        # Extract data from event
        detail = event.get('detail', {})
        customer_id = detail.get('customer_id')
        trigger_type = detail.get('trigger_type', 'new_invoice')
        risk_level = detail.get('risk_level', 'MEDIUM')
        invoice_data = detail.get('invoice_data', {})

        if not customer_id:
            raise ValueError("Missing customer_id in event")

        # Get customer information
        customer = get_customer_data(customer_id)

        # Generate email content based on trigger type
        email_content = generate_email_content(
            customer, trigger_type, risk_level, invoice_data
        )

        # Send email
        send_email(customer, email_content)

        # Log communication
        log_communication(customer_id, email_content, trigger_type)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Communication sent successfully',
                'customer_id': customer_id,
                'trigger_type': trigger_type
            })
        }

    except Exception as e:
        logger.error(f"Error in communication agent: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_customer_data(customer_id):
    """Retrieve customer data from DynamoDB"""
    try:
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            # Return default customer
            return {
                'customer_id': customer_id,
                'name': 'Valued Customer',
                'email': 'customer@example.com',
                'company': 'Unknown Company'
            }
        return response['Item']
    except Exception as e:
        logger.error(f"Error getting customer data: {str(e)}")
        raise


def generate_email_content(customer, trigger_type, risk_level, invoice_data):
    """Generate email content based on context"""

    # Try AI-powered content generation first
    try:
        if os.environ.get('USE_BEDROCK', 'false').lower() == 'true':
            return generate_ai_email(customer, trigger_type, risk_level, invoice_data)
    except Exception as e:
        logger.warning(f"AI email generation failed, using templates: {str(e)}")

    # Fallback to template-based content
    return generate_template_email(customer, trigger_type, risk_level, invoice_data)


def generate_template_email(customer, trigger_type, risk_level, invoice_data):
    """Generate email using templates"""

    customer_name = customer.get('name', 'Valued Customer')
    company_name = customer.get('company', '')

    templates = {
        'new_invoice': {
            'LOW': {
                'subject': f"Invoice {invoice_data.get('invoice_id')} from {COMPANY_NAME}",
                'body': f"""Dear {customer_name},

Thank you for your continued partnership with {COMPANY_NAME}.

We've issued a new invoice for your recent order:
- Invoice Number: {invoice_data.get('invoice_id')}
- Amount: ${invoice_data.get('amount', 0):.2f}
- Due Date: {invoice_data.get('due_date')}

As a valued customer with an excellent payment history, we appreciate your prompt attention to this invoice.

You can view and pay your invoice online through our customer portal.

Best regards,
The {COMPANY_NAME} Team"""
            },
            'MEDIUM': {
                'subject': f"Invoice {invoice_data.get('invoice_id')} - Payment Due {invoice_data.get('due_date')}",
                'body': f"""Dear {customer_name},

We've issued invoice {invoice_data.get('invoice_id')} for ${invoice_data.get('amount', 0):.2f}.

Payment Details:
- Invoice Number: {invoice_data.get('invoice_id')}
- Amount Due: ${invoice_data.get('amount', 0):.2f}
- Due Date: {invoice_data.get('due_date')}
- Payment Terms: Net 30

Please ensure payment is made by the due date to avoid any late fees.

If you have any questions about this invoice, please contact our billing department.

Thank you for your business.

Best regards,
The {COMPANY_NAME} Team"""
            },
            'HIGH': {
                'subject': f"Important: Invoice {invoice_data.get('invoice_id')} Requires Immediate Attention",
                'body': f"""Dear {customer_name},

We have issued invoice {invoice_data.get('invoice_id')} for ${invoice_data.get('amount', 0):.2f} with payment due by {invoice_data.get('due_date')}.

IMPORTANT PAYMENT INFORMATION:
- Invoice Number: {invoice_data.get('invoice_id')}
- Amount Due: ${invoice_data.get('amount', 0):.2f}
- Due Date: {invoice_data.get('due_date')}
- Payment Terms: Due upon receipt

To maintain your account in good standing, please arrange payment at your earliest convenience. We offer multiple payment options for your convenience:
- Bank transfer
- Credit card
- Online payment portal

If you're experiencing any difficulties with payment, please contact us immediately so we can work together on a solution.

We value your business and look forward to continuing our partnership.

Regards,
The {COMPANY_NAME} Accounts Team"""
            }
        },
        'payment_reminder': {
            'LOW': {
                'subject': f"Friendly Reminder: Invoice {invoice_data.get('invoice_id')}",
                'body': f"""Dear {customer_name},

This is a friendly reminder about invoice {invoice_data.get('invoice_id')} for ${invoice_data.get('amount', 0):.2f}.

If you've already sent payment, please disregard this message. Otherwise, we'd appreciate your attention to this matter at your earliest convenience.

Thank you for your continued partnership.

Best regards,
The {COMPANY_NAME} Team"""
            },
            'MEDIUM': {
                'subject': f"Payment Reminder: Invoice {invoice_data.get('invoice_id')} Due Soon",
                'body': f"""Dear {customer_name},

This is a reminder that invoice {invoice_data.get('invoice_id')} for ${invoice_data.get('amount', 0):.2f} is due for payment.

Please arrange payment to avoid any late fees or service interruption.

If you have any questions or concerns, please don't hesitate to contact us.

Thank you for your prompt attention to this matter.

Regards,
The {COMPANY_NAME} Billing Team"""
            },
            'HIGH': {
                'subject': f"Urgent: Overdue Invoice {invoice_data.get('invoice_id')} - Immediate Action Required",
                'body': f"""Dear {customer_name},

Our records indicate that invoice {invoice_data.get('invoice_id')} for ${invoice_data.get('amount', 0):.2f} is now overdue.

This requires your immediate attention to avoid:
- Late payment fees
- Service suspension
- Impact on credit terms

Please make payment immediately or contact us within 24 hours to discuss payment arrangements.

We value our business relationship and want to help resolve this matter quickly.

Urgent regards,
The {COMPANY_NAME} Collections Department"""
            }
        },
        'payment_confirmation': {
            'subject': f"Payment Received - Thank You!",
            'body': f"""Dear {customer_name},

We've received your payment for invoice {invoice_data.get('invoice_id')}.

Payment Details:
- Amount Received: ${invoice_data.get('amount', 0):.2f}
- Invoice Number: {invoice_data.get('invoice_id')}
- Payment Date: {datetime.now().strftime('%Y-%m-%d')}

Thank you for your prompt payment. We appreciate your business and look forward to continuing to serve you.

Best regards,
The {COMPANY_NAME} Team"""
        }
    }

    # Get appropriate template
    if trigger_type == 'payment_confirmation':
        template = templates['payment_confirmation']
    else:
        template_group = templates.get(trigger_type, templates['new_invoice'])
        template = template_group.get(risk_level, template_group['MEDIUM'])

    return template


def generate_ai_email(customer, trigger_type, risk_level, invoice_data):
    """Generate AI-powered personalized email"""

    prompt = f"""
    Generate a professional email for the following scenario:

    Customer: {customer.get('name')} from {customer.get('company')}
    Trigger: {trigger_type}
    Risk Level: {risk_level}
    Invoice Amount: ${invoice_data.get('amount', 0)}
    Due Date: {invoice_data.get('due_date')}

    Context:
    - This is a {trigger_type.replace('_', ' ')} email
    - The customer has a {risk_level} risk profile
    - Tone should be {'friendly and appreciative' if risk_level == 'LOW' else 'professional and firm' if risk_level == 'HIGH' else 'professional and courteous'}

    Generate a subject line and email body that is professional, clear, and appropriate for the risk level.
    Format as JSON with 'subject' and 'body' fields.
    """

    try:
        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'prompt': prompt,
                'max_tokens_to_sample': 500,
                'temperature': 0.7
            })
        )

        result = json.loads(response['body'].read())
        email_content = json.loads(result.get('completion', '{}'))

        return {
            'subject': email_content.get('subject', f"Invoice {invoice_data.get('invoice_id')}"),
            'body': email_content.get('body', 'Please contact us regarding your invoice.')
        }

    except Exception as e:
        logger.error(f"AI email generation failed: {str(e)}")
        raise


def send_email(customer, email_content):
    """Send email using SES"""
    try:
        customer_email = customer.get('email', 'customer@example.com')

        response = ses.send_email(
            Source=VERIFIED_EMAIL,
            Destination={'ToAddresses': [customer_email]},
            Message={
                'Subject': {'Data': email_content['subject']},
                'Body': {'Text': {'Data': email_content['body']}}
            }
        )

        logger.info(f"Email sent to {customer_email}, MessageId: {response['MessageId']}")
        return response['MessageId']

    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise


def log_communication(customer_id, email_content, trigger_type):
    """Log communication in DynamoDB"""
    try:
        item = {
            'communication_id': str(uuid.uuid4()),
            'customer_id': customer_id,
            'communication_type': 'email',
            'trigger_type': trigger_type,
            'subject': email_content['subject'],
            'content': email_content['body'],
            'sent_date': datetime.now().isoformat(),
            'status': 'sent'
        }

        communications_table.put_item(Item=item)
        logger.info(f"Communication logged for customer {customer_id}")

    except Exception as e:
        logger.error(f"Error logging communication: {str(e)}")
        # Don't raise - logging failure shouldn't stop the process