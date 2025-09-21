"""Receipt Processing Agent Lambda Function

Processes payment receipts using OCR and AI to extract payment information
"""

import json
import boto3
import os
from datetime import datetime
from decimal import Decimal
import logging
import uuid
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')
textract = boto3.client('textract', region_name='ap-southeast-1')
dynamodb = boto3.resource('dynamodb')
events = boto3.client('events')
bedrock = boto3.client('bedrock-runtime', region_name='ap-southeast-1')

# DynamoDB tables
invoices_table = dynamodb.Table('BillingInvoices')
payment_records_table = dynamodb.Table('PaymentRecords')

# Configuration
S3_BUCKET = os.environ.get('S3_BUCKET', 'billing-receipts')
EVENT_BUS_NAME = 'billing-events'


def lambda_handler(event, context):
    """Main Lambda handler for receipt processing"""
    logger.info(f"Receipt Processing Agent triggered with event: {json.dumps(event)}")

    try:
        # Extract data from event
        detail = event.get('detail', {})
        receipt_image_key = detail.get('receipt_image_key')
        customer_id = detail.get('customer_id')
        reference_invoice = detail.get('reference_invoice')

        if not receipt_image_key:
            raise ValueError("Missing receipt_image_key in event")

        # Extract text from receipt
        receipt_text = extract_text_from_receipt(receipt_image_key)

        # Parse payment information
        payment_info = parse_payment_information(receipt_text, reference_invoice)

        # Update invoice status
        update_invoice_status(payment_info['invoice_id'], payment_info)

        # Store payment record
        store_payment_record(customer_id, payment_info)

        # Trigger payment confirmation email
        trigger_payment_confirmation(customer_id, payment_info)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Receipt processed successfully',
                'payment_info': convert_decimals(payment_info)
            })
        }

    except Exception as e:
        logger.error(f"Error processing receipt: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def extract_text_from_receipt(image_key):
    """Extract text from receipt image using Textract or fallback"""

    try:
        if os.environ.get('USE_TEXTRACT', 'false').lower() == 'true':
            return extract_with_textract(image_key)
    except Exception as e:
        logger.warning(f"Textract extraction failed, using fallback: {str(e)}")

    # Fallback to mock extraction for demo
    return extract_with_fallback(image_key)


def extract_with_textract(image_key):
    """Extract text using AWS Textract"""
    try:
        # Call Textract
        response = textract.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': S3_BUCKET,
                    'Name': image_key
                }
            }
        )

        # Extract text from response
        text_lines = []
        for block in response.get('Blocks', []):
            if block['BlockType'] == 'LINE':
                text_lines.append(block['Text'])

        full_text = '\n'.join(text_lines)
        logger.info(f"Textract extracted {len(text_lines)} lines of text")

        return full_text

    except Exception as e:
        logger.error(f"Textract error: {str(e)}")
        raise


def extract_with_fallback(image_key):
    """Fallback text extraction (mock for demo)"""

    # In production, you might use alternative OCR libraries
    # For demo, return sample receipt text
    sample_text = """
    PAYMENT RECEIPT
    Date: 2024-09-20

    Transaction Details:
    Reference: INV-2024-001
    Amount: RM 1,500.00
    Payment Method: Bank Transfer
    Transaction ID: TXN123456789

    Payer: ABC Corp
    Bank: Maybank

    Status: SUCCESSFUL

    Thank you for your payment!
    """

    logger.info("Using fallback text extraction")
    return sample_text


def parse_payment_information(receipt_text, reference_invoice):
    """Parse payment information from receipt text"""

    # Try AI parsing first
    try:
        if os.environ.get('USE_BEDROCK', 'false').lower() == 'true':
            return parse_with_ai(receipt_text, reference_invoice)
    except Exception as e:
        logger.warning(f"AI parsing failed, using regex: {str(e)}")

    # Fallback to regex parsing
    return parse_with_regex(receipt_text, reference_invoice)


def parse_with_regex(receipt_text, reference_invoice):
    """Parse payment information using regex patterns"""

    payment_info = {
        'invoice_id': reference_invoice,
        'amount': 0,
        'payment_date': datetime.now().isoformat(),
        'payment_method': 'unknown',
        'transaction_id': str(uuid.uuid4()),
        'currency': 'MYR'
    }

    # Extract invoice reference
    invoice_pattern = r'(?:Invoice|Reference|INV)[\s:#-]*([A-Z0-9-]+)'
    invoice_match = re.search(invoice_pattern, receipt_text, re.IGNORECASE)
    if invoice_match:
        payment_info['invoice_id'] = invoice_match.group(1)

    # Extract amount (supports RM format)
    amount_pattern = r'(?:RM|MYR|Amount)[\s:]*([0-9,]+(?:\.[0-9]{2})?)'
    amount_match = re.search(amount_pattern, receipt_text, re.IGNORECASE)
    if amount_match:
        amount_str = amount_match.group(1).replace(',', '')
        payment_info['amount'] = float(amount_str)

    # Extract date
    date_pattern = r'(?:Date|Payment Date)[\s:]*([0-9]{4}-[0-9]{2}-[0-9]{2})'
    date_match = re.search(date_pattern, receipt_text, re.IGNORECASE)
    if date_match:
        payment_info['payment_date'] = date_match.group(1)

    # Extract payment method
    method_pattern = r'(?:Payment Method|Method|Via)[\s:]*([A-Za-z\s]+)'
    method_match = re.search(method_pattern, receipt_text, re.IGNORECASE)
    if method_match:
        payment_info['payment_method'] = method_match.group(1).strip()

    # Extract transaction ID
    txn_pattern = r'(?:Transaction|TXN|Ref)[\s:#]*([A-Z0-9]{6,})'
    txn_match = re.search(txn_pattern, receipt_text, re.IGNORECASE)
    if txn_match:
        payment_info['transaction_id'] = txn_match.group(1)

    # Malaysian payment methods detection
    if any(bank in receipt_text.upper() for bank in ['MAYBANK', 'CIMB', 'PUBLIC BANK', 'RHB']):
        payment_info['payment_method'] = 'Bank Transfer'
    elif 'DUITNOW' in receipt_text.upper():
        payment_info['payment_method'] = 'DuitNow'
    elif any(card in receipt_text.upper() for card in ['VISA', 'MASTERCARD', 'AMEX']):
        payment_info['payment_method'] = 'Credit Card'

    logger.info(f"Parsed payment info: {payment_info}")
    return payment_info


def parse_with_ai(receipt_text, reference_invoice):
    """Parse payment information using AI"""

    prompt = f"""
    Extract payment information from the following receipt text:

    Receipt Text:
    {receipt_text}

    Reference Invoice: {reference_invoice}

    Please extract:
    1. Invoice ID/Reference
    2. Payment amount (numeric value)
    3. Payment date (YYYY-MM-DD format)
    4. Payment method
    5. Transaction ID
    6. Currency (default to MYR if Malaysian receipt)

    Respond in JSON format with these exact fields:
    invoice_id, amount, payment_date, payment_method, transaction_id, currency
    """

    try:
        response = bedrock.invoke_model(
            modelId='anthropic.claude-v2',
            contentType='application/json',
            accept='application/json',
            body=json.dumps({
                'prompt': prompt,
                'max_tokens_to_sample': 300,
                'temperature': 0.3
            })
        )

        result = json.loads(response['body'].read())
        payment_info = json.loads(result.get('completion', '{}'))

        # Ensure all required fields
        payment_info.setdefault('invoice_id', reference_invoice)
        payment_info.setdefault('amount', 0)
        payment_info.setdefault('payment_date', datetime.now().isoformat())
        payment_info.setdefault('payment_method', 'unknown')
        payment_info.setdefault('transaction_id', str(uuid.uuid4()))
        payment_info.setdefault('currency', 'MYR')

        return payment_info

    except Exception as e:
        logger.error(f"AI parsing failed: {str(e)}")
        raise


def update_invoice_status(invoice_id, payment_info):
    """Update invoice status to paid"""
    try:
        response = invoices_table.update_item(
            Key={'invoice_id': invoice_id},
            UpdateExpression='SET #status = :status, payment_date = :payment_date, amount_paid = :amount',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={
                ':status': 'paid',
                ':payment_date': payment_info['payment_date'],
                ':amount': Decimal(str(payment_info['amount']))
            }
        )

        logger.info(f"Invoice {invoice_id} marked as paid")

    except Exception as e:
        logger.error(f"Error updating invoice: {str(e)}")
        # Continue processing even if update fails


def store_payment_record(customer_id, payment_info):
    """Store payment record in DynamoDB"""
    try:
        item = {
            'transaction_id': payment_info['transaction_id'],
            'customer_id': customer_id,
            'invoice_id': payment_info['invoice_id'],
            'amount': Decimal(str(payment_info['amount'])),
            'currency': payment_info['currency'],
            'payment_date': payment_info['payment_date'],
            'payment_method': payment_info['payment_method'],
            'processed_date': datetime.now().isoformat(),
            'status': 'completed'
        }

        payment_records_table.put_item(Item=item)
        logger.info(f"Payment record stored: {payment_info['transaction_id']}")

    except Exception as e:
        logger.error(f"Error storing payment record: {str(e)}")
        raise


def trigger_payment_confirmation(customer_id, payment_info):
    """Trigger payment confirmation email"""
    try:
        event = {
            'Source': 'billing.payment.received',
            'DetailType': 'Payment Confirmation Required',
            'EventBusName': EVENT_BUS_NAME,
            'Detail': json.dumps({
                'customer_id': customer_id,
                'invoice_data': {
                    'invoice_id': payment_info['invoice_id'],
                    'amount': float(payment_info['amount'])
                },
                'trigger_type': 'payment_confirmation',
                'payment_info': convert_decimals(payment_info),
                'timestamp': datetime.now().isoformat()
            })
        }

        response = events.put_events(Entries=[event])
        logger.info(f"Payment confirmation event triggered for {customer_id}")

    except Exception as e:
        logger.error(f"Error triggering confirmation: {str(e)}")
        # Don't raise - confirmation failure shouldn't stop the process


def convert_decimals(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    return obj