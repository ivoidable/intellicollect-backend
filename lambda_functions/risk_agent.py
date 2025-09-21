"""Risk Assessment Agent Lambda Function

Analyzes customer payment risk based on payment history and account age.
Assigns risk levels: HIGH, MEDIUM, LOW
"""

import json
import boto3
import os
from datetime import datetime, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
events = boto3.client('events')
bedrock = boto3.client('bedrock-runtime', region_name='ap-southeast-1')

# DynamoDB tables
customers_table = dynamodb.Table('BillingCustomers')
invoices_table = dynamodb.Table('BillingInvoices')
risk_scores_table = dynamodb.Table('RiskScores')

# Event bus
EVENT_BUS_NAME = 'billing-events'


def lambda_handler(event, context):
    """Main Lambda handler for risk assessment"""
    logger.info(f"Risk Agent triggered with event: {json.dumps(event)}")

    try:
        # Extract data from event
        detail = event.get('detail', {})
        customer_id = detail.get('customer_id')
        invoice_data = detail.get('invoice_data', {})

        if not customer_id:
            raise ValueError("Missing customer_id in event")

        # Get customer information
        customer = get_customer_data(customer_id)

        # Get payment history
        payment_history = get_payment_history(customer_id)

        # Calculate risk score
        risk_assessment = assess_risk(customer, payment_history, invoice_data)

        # Store risk assessment
        store_risk_assessment(customer_id, risk_assessment)

        # Publish event for communication agent
        publish_risk_assessment_complete(customer_id, risk_assessment, invoice_data)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Risk assessment completed',
                'customer_id': customer_id,
                'risk_level': risk_assessment['risk_level'],
                'risk_score': risk_assessment['risk_score']
            })
        }

    except Exception as e:
        logger.error(f"Error in risk assessment: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def get_customer_data(customer_id):
    """Retrieve customer data from DynamoDB"""
    try:
        response = customers_table.get_item(Key={'customer_id': customer_id})
        if 'Item' not in response:
            # Create default customer if not exists
            customer = {
                'customer_id': customer_id,
                'created_date': datetime.now().isoformat(),
                'payment_history': 'unknown'
            }
            customers_table.put_item(Item=customer)
            return customer
        return response['Item']
    except Exception as e:
        logger.error(f"Error getting customer data: {str(e)}")
        raise


def get_payment_history(customer_id):
    """Get payment history for customer"""
    try:
        response = invoices_table.query(
            IndexName='CustomerIndex',
            KeyConditionExpression='customer_id = :cid',
            ExpressionAttributeValues={':cid': customer_id}
        )

        invoices = response.get('Items', [])

        # Calculate payment statistics
        total_invoices = len(invoices)
        paid_on_time = sum(1 for inv in invoices
                          if inv.get('status') == 'paid'
                          and inv.get('payment_date', '') <= inv.get('due_date', ''))
        overdue_invoices = sum(1 for inv in invoices if inv.get('status') == 'overdue')

        return {
            'total_invoices': total_invoices,
            'paid_on_time': paid_on_time,
            'overdue_invoices': overdue_invoices,
            'payment_rate': (paid_on_time / total_invoices * 100) if total_invoices > 0 else 0
        }

    except Exception as e:
        logger.error(f"Error getting payment history: {str(e)}")
        return {
            'total_invoices': 0,
            'paid_on_time': 0,
            'overdue_invoices': 0,
            'payment_rate': 0
        }


def assess_risk(customer, payment_history, invoice_data):
    """Assess customer risk using AI or fallback rules"""

    # Try AI assessment first
    try:
        if os.environ.get('USE_BEDROCK', 'false').lower() == 'true':
            return assess_risk_with_ai(customer, payment_history, invoice_data)
    except Exception as e:
        logger.warning(f"AI assessment failed, using rule-based: {str(e)}")

    # Fallback to rule-based assessment
    return assess_risk_with_rules(customer, payment_history, invoice_data)


def assess_risk_with_rules(customer, payment_history, invoice_data):
    """Rule-based risk assessment fallback"""

    risk_score = 50  # Base score

    # Account age factor
    created_date = customer.get('created_date', datetime.now().isoformat())
    account_age_days = (datetime.now() - datetime.fromisoformat(created_date)).days

    if account_age_days < 30:
        risk_score += 20  # New customers are higher risk
    elif account_age_days < 90:
        risk_score += 10
    elif account_age_days > 365:
        risk_score -= 10  # Long-term customers are lower risk

    # Payment history factor
    payment_rate = payment_history.get('payment_rate', 0)
    overdue_count = payment_history.get('overdue_invoices', 0)

    if payment_rate >= 90:
        risk_score -= 20
    elif payment_rate >= 70:
        risk_score -= 10
    elif payment_rate < 50:
        risk_score += 20

    if overdue_count > 3:
        risk_score += 25
    elif overdue_count > 1:
        risk_score += 15

    # Invoice amount factor
    amount = float(invoice_data.get('amount', 0))
    if amount > 10000:
        risk_score += 15
    elif amount > 5000:
        risk_score += 10

    # Normalize score
    risk_score = max(0, min(100, risk_score))

    # Determine risk level
    if risk_score >= 70:
        risk_level = 'HIGH'
    elif risk_score >= 40:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'

    return {
        'risk_score': risk_score,
        'risk_level': risk_level,
        'assessment_method': 'rule_based',
        'factors': {
            'account_age_days': account_age_days,
            'payment_rate': payment_rate,
            'overdue_count': overdue_count,
            'invoice_amount': amount
        }
    }


def assess_risk_with_ai(customer, payment_history, invoice_data):
    """AI-powered risk assessment using Bedrock"""

    prompt = f"""
    Analyze the following customer data and provide a risk assessment:

    Customer Information:
    - Account age: {customer.get('created_date')}
    - Payment history: {customer.get('payment_history', 'unknown')}
    - Industry: {customer.get('industry', 'unknown')}

    Payment Statistics:
    - Total invoices: {payment_history['total_invoices']}
    - Paid on time: {payment_history['paid_on_time']}
    - Overdue invoices: {payment_history['overdue_invoices']}
    - Payment rate: {payment_history['payment_rate']}%

    Current Invoice:
    - Amount: ${invoice_data.get('amount', 0)}
    - Due date: {invoice_data.get('due_date')}

    Based on this information, provide:
    1. Risk score (0-100)
    2. Risk level (HIGH/MEDIUM/LOW)
    3. Key risk factors

    Respond in JSON format.
    """

    try:
        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'prompt': prompt,
                'max_tokens_to_sample': 500,
                'temperature': 0.5
            })
        )

        result = json.loads(response['body'].read())
        ai_assessment = json.loads(result.get('completion', '{}'))

        return {
            'risk_score': ai_assessment.get('risk_score', 50),
            'risk_level': ai_assessment.get('risk_level', 'MEDIUM'),
            'assessment_method': 'ai_powered',
            'factors': ai_assessment.get('factors', {})
        }

    except Exception as e:
        logger.error(f"Bedrock AI assessment failed: {str(e)}")
        raise


def store_risk_assessment(customer_id, assessment):
    """Store risk assessment in DynamoDB"""
    try:
        item = {
            'customer_id': customer_id,
            'assessment_date': datetime.now().isoformat(),
            'risk_score': Decimal(str(assessment['risk_score'])),
            'risk_level': assessment['risk_level'],
            'assessment_method': assessment['assessment_method'],
            'factors': assessment['factors']
        }

        risk_scores_table.put_item(Item=item)
        logger.info(f"Risk assessment stored for customer {customer_id}")

    except Exception as e:
        logger.error(f"Error storing risk assessment: {str(e)}")
        raise


def publish_risk_assessment_complete(customer_id, assessment, invoice_data):
    """Publish event to trigger communication agent"""
    try:
        event = {
            'Source': 'billing.risk.agent',
            'DetailType': 'Risk Assessment Complete',
            'EventBusName': EVENT_BUS_NAME,
            'Detail': json.dumps({
                'customer_id': customer_id,
                'risk_level': assessment['risk_level'],
                'risk_score': assessment['risk_score'],
                'invoice_data': invoice_data,
                'trigger_type': 'new_invoice',
                'timestamp': datetime.now().isoformat()
            })
        }

        response = events.put_events(Entries=[event])
        logger.info(f"Published risk assessment complete event for {customer_id}")

    except Exception as e:
        logger.error(f"Error publishing event: {str(e)}")
        raise