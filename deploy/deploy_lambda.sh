#!/bin/bash

# Lambda Deployment Script for Billing Intelligence System
# Usage: ./deploy_lambda.sh [function-name|all]

set -e

# Configuration
REGION="ap-southeast-1"
RUNTIME="python3.12"
TIMEOUT_RISK=30
TIMEOUT_COMM=60
TIMEOUT_RECEIPT=120
MEMORY_SIZE_DEFAULT=128
MEMORY_SIZE_RECEIPT=512

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/BillingAgentRole"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}AWS Billing Intelligence System - Lambda Deployment${NC}"
echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo "Role: $ROLE_ARN"
echo ""

# Function to create deployment package
create_deployment_package() {
    local function_name=$1
    local source_file="../app/lambda_functions/${function_name}.py"
    local zip_file="${function_name}.zip"

    echo -e "${YELLOW}Creating deployment package for ${function_name}...${NC}"

    # Create temporary directory
    temp_dir=$(mktemp -d)

    # Copy function code
    cp "$source_file" "$temp_dir/lambda_function.py"

    # Add requirements if needed
    if [ -f "../app/lambda_functions/requirements_${function_name}.txt" ]; then
        pip install -r "../app/lambda_functions/requirements_${function_name}.txt" -t "$temp_dir" --quiet
    fi

    # Create zip file
    cd "$temp_dir"
    zip -r "$zip_file" . -q
    mv "$zip_file" "$OLDPWD/"
    cd "$OLDPWD"

    # Clean up
    rm -rf "$temp_dir"

    echo -e "${GREEN}✓ Package created: ${zip_file}${NC}"
}

# Function to deploy Lambda function
deploy_function() {
    local function_name=$1
    local handler="lambda_function.lambda_handler"
    local timeout=$2
    local memory_size=$3
    local zip_file="${function_name}.zip"

    echo -e "${YELLOW}Deploying ${function_name}...${NC}"

    # Create deployment package
    create_deployment_package "$function_name"

    # Check if function exists
    if aws lambda get-function --function-name "$function_name" --region "$REGION" 2>/dev/null; then
        # Update existing function
        echo "Updating existing function..."
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://${zip_file}" \
            --region "$REGION" \
            --output table

        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --timeout "$timeout" \
            --memory-size "$memory_size" \
            --region "$REGION" \
            --output table
    else
        # Create new function
        echo "Creating new function..."
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime "$RUNTIME" \
            --role "$ROLE_ARN" \
            --handler "$handler" \
            --zip-file "fileb://${zip_file}" \
            --timeout "$timeout" \
            --memory-size "$memory_size" \
            --region "$REGION" \
            --output table
    fi

    # Clean up zip file
    rm -f "$zip_file"

    echo -e "${GREEN}✓ ${function_name} deployed successfully${NC}"
    echo ""
}

# Function to set environment variables
set_environment_variables() {
    local function_name=$1

    echo -e "${YELLOW}Setting environment variables for ${function_name}...${NC}"

    case "$function_name" in
        "communication-agent")
            aws lambda update-function-configuration \
                --function-name "$function_name" \
                --environment "Variables={VERIFIED_EMAIL=billing@yourcompany.com,COMPANY_NAME=YourCompany,USE_BEDROCK=false}" \
                --region "$REGION" \
                --output table
            ;;
        "receipt-processing-agent")
            aws lambda update-function-configuration \
                --function-name "$function_name" \
                --environment "Variables={S3_BUCKET=billing-receipts,USE_TEXTRACT=false,USE_BEDROCK=false}" \
                --region "$REGION" \
                --output table
            ;;
        "risk-agent")
            aws lambda update-function-configuration \
                --function-name "$function_name" \
                --environment "Variables={USE_BEDROCK=false}" \
                --region "$REGION" \
                --output table
            ;;
    esac

    echo -e "${GREEN}✓ Environment variables set${NC}"
}

# Main deployment logic
case "$1" in
    "risk-agent")
        deploy_function "risk-agent" "$TIMEOUT_RISK" "$MEMORY_SIZE_DEFAULT"
        set_environment_variables "risk-agent"
        ;;
    "communication-agent")
        deploy_function "communication-agent" "$TIMEOUT_COMM" "$MEMORY_SIZE_DEFAULT"
        set_environment_variables "communication-agent"
        ;;
    "receipt-processing-agent")
        deploy_function "receipt-processing-agent" "$TIMEOUT_RECEIPT" "$MEMORY_SIZE_RECEIPT"
        set_environment_variables "receipt-processing-agent"
        ;;
    "all"|"")
        echo -e "${GREEN}Deploying all Lambda functions...${NC}"
        echo ""
        deploy_function "risk-agent" "$TIMEOUT_RISK" "$MEMORY_SIZE_DEFAULT"
        set_environment_variables "risk-agent"
        deploy_function "communication-agent" "$TIMEOUT_COMM" "$MEMORY_SIZE_DEFAULT"
        set_environment_variables "communication-agent"
        deploy_function "receipt-processing-agent" "$TIMEOUT_RECEIPT" "$MEMORY_SIZE_RECEIPT"
        set_environment_variables "receipt-processing-agent"
        echo -e "${GREEN}All functions deployed successfully!${NC}"
        ;;
    *)
        echo -e "${RED}Unknown function: $1${NC}"
        echo "Usage: $0 [risk-agent|communication-agent|receipt-processing-agent|all]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}Deployment complete!${NC}"
echo ""
echo "Next steps:"
echo "1. Configure EventBridge rules using setup_eventbridge.sh"
echo "2. Update environment variables with your actual values"
echo "3. Test the functions using test_lambda.sh"