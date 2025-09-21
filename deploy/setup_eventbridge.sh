#!/bin/bash

# EventBridge Setup Script for Billing Intelligence System

set -e

# Configuration
REGION="ap-southeast-1"
EVENT_BUS_NAME="billing-events"

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}AWS EventBridge Setup for Billing Intelligence System${NC}"
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Event Bus: $EVENT_BUS_NAME"
echo ""

# Create custom event bus
echo -e "${YELLOW}Creating custom event bus...${NC}"
aws events create-event-bus --name "$EVENT_BUS_NAME" --region "$REGION" 2>/dev/null || \
    echo "Event bus already exists"

# Get Lambda function ARNs
RISK_AGENT_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:risk-agent"
COMM_AGENT_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:communication-agent"
RECEIPT_AGENT_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:receipt-processing-agent"

# Create EventBridge Rules

echo -e "${YELLOW}Creating EventBridge rules...${NC}"

# 1. Invoice Created Rule
echo "Creating InvoiceCreatedRule..."
aws events put-rule \
    --name InvoiceCreatedRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --event-pattern '{
        "source": ["billing.invoice.created"],
        "detail-type": ["New Invoice Generated"]
    }' \
    --state ENABLED \
    --description "Trigger risk assessment when new invoice is created" \
    --region "$REGION"

aws events put-targets \
    --rule InvoiceCreatedRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --targets "Id=1,Arn=${RISK_AGENT_ARN}" \
    --region "$REGION"

# 2. Communication Trigger Rule
echo "Creating CommunicationTriggerRule..."
aws events put-rule \
    --name CommunicationTriggerRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --event-pattern '{
        "source": ["billing.risk.agent"],
        "detail-type": ["Risk Assessment Complete"]
    }' \
    --state ENABLED \
    --description "Trigger communication after risk assessment" \
    --region "$REGION"

aws events put-targets \
    --rule CommunicationTriggerRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --targets "Id=1,Arn=${COMM_AGENT_ARN}" \
    --region "$REGION"

# 3. Receipt Processing Rule
echo "Creating ReceiptProcessingRule..."
aws events put-rule \
    --name ReceiptProcessingRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --event-pattern '{
        "source": ["billing.receipt.uploaded"],
        "detail-type": ["Payment Receipt Received"]
    }' \
    --state ENABLED \
    --description "Process payment receipts" \
    --region "$REGION"

aws events put-targets \
    --rule ReceiptProcessingRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --targets "Id=1,Arn=${RECEIPT_AGENT_ARN}" \
    --region "$REGION"

# 4. Payment Confirmation Rule
echo "Creating PaymentConfirmationRule..."
aws events put-rule \
    --name PaymentConfirmationRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --event-pattern '{
        "source": ["billing.payment.received"],
        "detail-type": ["Payment Confirmation Required"]
    }' \
    --state ENABLED \
    --description "Send payment confirmation emails" \
    --region "$REGION"

aws events put-targets \
    --rule PaymentConfirmationRule \
    --event-bus-name "$EVENT_BUS_NAME" \
    --targets "Id=1,Arn=${COMM_AGENT_ARN}" \
    --region "$REGION"

echo -e "${GREEN}✓ EventBridge rules created${NC}"
echo ""

# Grant Lambda permissions for EventBridge
echo -e "${YELLOW}Granting Lambda permissions...${NC}"

# Risk Agent permissions
aws lambda add-permission \
    --function-name risk-agent \
    --statement-id allow-eventbridge-invoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${EVENT_BUS_NAME}/InvoiceCreatedRule" \
    --region "$REGION" 2>/dev/null || echo "Permission already exists"

# Communication Agent permissions
aws lambda add-permission \
    --function-name communication-agent \
    --statement-id allow-eventbridge-invoke-risk \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${EVENT_BUS_NAME}/CommunicationTriggerRule" \
    --region "$REGION" 2>/dev/null || echo "Permission already exists"

aws lambda add-permission \
    --function-name communication-agent \
    --statement-id allow-eventbridge-invoke-payment \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${EVENT_BUS_NAME}/PaymentConfirmationRule" \
    --region "$REGION" 2>/dev/null || echo "Permission already exists"

# Receipt Processing Agent permissions
aws lambda add-permission \
    --function-name receipt-processing-agent \
    --statement-id allow-eventbridge-invoke \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${EVENT_BUS_NAME}/ReceiptProcessingRule" \
    --region "$REGION" 2>/dev/null || echo "Permission already exists"

echo -e "${GREEN}✓ Lambda permissions granted${NC}"
echo ""

# List all rules
echo -e "${GREEN}EventBridge Rules Summary:${NC}"
aws events list-rules --event-bus-name "$EVENT_BUS_NAME" --region "$REGION" --output table

echo ""
echo -e "${GREEN}EventBridge setup complete!${NC}"
echo ""
echo "You can now trigger events using:"
echo "  aws events put-events --entries file://sample-events.json"