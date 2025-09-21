"""DynamoDB Table Definitions

This module defines the DynamoDB tables for the BillingIQ system.
We use a single-table design pattern with composite keys for efficiency.
"""

from typing import Dict, Any, List
from enum import Enum


class TableNames:
    """DynamoDB table names"""
    MAIN = "BillingIQ-Main"  # Main table for all business entities
    AUDIT = "BillingIQ-Audit"  # Separate table for audit logs
    METRICS = "BillingIQ-Metrics"  # Time-series metrics and analytics


class EntityTypes:
    """Entity type prefixes for partition keys"""
    USER = "USER"
    COMPANY = "COMPANY"
    CUSTOMER = "CUSTOMER"
    INVOICE = "INVOICE"
    INVOICE_ITEM = "INVOICE_ITEM"
    PAYMENT = "PAYMENT"
    RISK_ASSESSMENT = "RISK"
    AI_INSIGHT = "INSIGHT"
    RECEIPT = "RECEIPT"
    SETTING = "SETTING"
    API_TOKEN = "TOKEN"
    TOKEN_USAGE = "USAGE"
    USER_COMPANY = "USER_COMPANY"
    COMMUNICATION = "COMM"


class GSINames:
    """Global Secondary Index names"""
    GSI1 = "GSI1-Index"  # For inverse queries
    GSI2 = "GSI2-Index"  # For status-based queries
    GSI3 = "GSI3-Index"  # For date-range queries
    GSI4 = "GSI4-Index"  # For email lookups
    GSI5 = "GSI5-Index"  # For company-wide queries


# Main table schema definition
MAIN_TABLE_SCHEMA = {
    "TableName": TableNames.MAIN,
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},  # Partition Key
        {"AttributeName": "SK", "KeyType": "RANGE"}   # Sort Key
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "GSI1PK", "AttributeType": "S"},
        {"AttributeName": "GSI1SK", "AttributeType": "S"},
        {"AttributeName": "GSI2PK", "AttributeType": "S"},
        {"AttributeName": "GSI2SK", "AttributeType": "S"},
        {"AttributeName": "GSI3PK", "AttributeType": "S"},
        {"AttributeName": "GSI3SK", "AttributeType": "S"},
        {"AttributeName": "GSI4PK", "AttributeType": "S"},
        {"AttributeName": "GSI4SK", "AttributeType": "S"},
        {"AttributeName": "GSI5PK", "AttributeType": "S"},
        {"AttributeName": "GSI5SK", "AttributeType": "S"},
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": GSINames.GSI1,
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": GSINames.GSI2,
            "KeySchema": [
                {"AttributeName": "GSI2PK", "KeyType": "HASH"},
                {"AttributeName": "GSI2SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": GSINames.GSI3,
            "KeySchema": [
                {"AttributeName": "GSI3PK", "KeyType": "HASH"},
                {"AttributeName": "GSI3SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": GSINames.GSI4,
            "KeySchema": [
                {"AttributeName": "GSI4PK", "KeyType": "HASH"},
                {"AttributeName": "GSI4SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": GSINames.GSI5,
            "KeySchema": [
                {"AttributeName": "GSI5PK", "KeyType": "HASH"},
                {"AttributeName": "GSI5SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        }
    ],
    "BillingMode": "PAY_PER_REQUEST",  # On-demand billing
    "StreamSpecification": {
        "StreamEnabled": True,
        "StreamViewType": "NEW_AND_OLD_IMAGES"
    },
    "Tags": [
        {"Key": "Application", "Value": "BillingIQ"},
        {"Key": "Environment", "Value": "Production"}
    ]
}

# Audit table schema
AUDIT_TABLE_SCHEMA = {
    "TableName": TableNames.AUDIT,
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},  # AUDIT#<company_id>
        {"AttributeName": "SK", "KeyType": "RANGE"}   # <timestamp>#<audit_id>
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"},
        {"AttributeName": "UserID", "AttributeType": "S"},
        {"AttributeName": "EntityType", "AttributeType": "S"}
    ],
    "GlobalSecondaryIndexes": [
        {
            "IndexName": "UserIndex",
            "KeySchema": [
                {"AttributeName": "UserID", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        },
        {
            "IndexName": "EntityIndex",
            "KeySchema": [
                {"AttributeName": "EntityType", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"}
            ],
            "Projection": {"ProjectionType": "ALL"},
            "ProvisionedThroughput": {
                "ReadCapacityUnits": 5,
                "WriteCapacityUnits": 5
            }
        }
    ],
    "BillingMode": "PAY_PER_REQUEST",
    "StreamSpecification": {
        "StreamEnabled": True,
        "StreamViewType": "NEW_IMAGE"
    },
    "Tags": [
        {"Key": "Application", "Value": "BillingIQ"},
        {"Key": "Type", "Value": "Audit"}
    ]
}

# Metrics table schema for time-series data
METRICS_TABLE_SCHEMA = {
    "TableName": TableNames.METRICS,
    "KeySchema": [
        {"AttributeName": "PK", "KeyType": "HASH"},  # METRIC#<company_id>#<metric_type>
        {"AttributeName": "SK", "KeyType": "RANGE"}   # <timestamp>
    ],
    "AttributeDefinitions": [
        {"AttributeName": "PK", "AttributeType": "S"},
        {"AttributeName": "SK", "AttributeType": "S"}
    ],
    "BillingMode": "PAY_PER_REQUEST",
    "TimeToLiveSpecification": {
        "AttributeName": "TTL",
        "Enabled": True
    },
    "Tags": [
        {"Key": "Application", "Value": "BillingIQ"},
        {"Key": "Type", "Value": "Metrics"}
    ]
}


class AccessPatterns:
    """
    DynamoDB Access Patterns Documentation

    Main Table Access Patterns:

    1. Get user by ID:
       PK: USER#<user_id>, SK: METADATA

    2. Get user by email:
       GSI4PK: EMAIL#<email>, GSI4SK: USER

    3. Get all companies for a user:
       GSI1PK: USER#<user_id>, GSI1SK: COMPANY#

    4. Get all users in a company:
       GSI1PK: COMPANY#<company_id>, GSI1SK: USER#

    5. Get company by ID:
       PK: COMPANY#<company_id>, SK: METADATA

    6. Get all customers for a company:
       PK: COMPANY#<company_id>, SK: CUSTOMER#

    7. Get customer by ID:
       PK: CUSTOMER#<customer_id>, SK: METADATA

    8. Get all invoices for a company:
       GSI5PK: COMPANY#<company_id>, GSI5SK: INVOICE#

    9. Get all invoices for a customer:
       GSI1PK: CUSTOMER#<customer_id>, GSI1SK: INVOICE#

    10. Get invoice by ID:
        PK: INVOICE#<invoice_id>, SK: METADATA

    11. Get invoice items:
        PK: INVOICE#<invoice_id>, SK: ITEM#

    12. Get invoices by status:
        GSI2PK: STATUS#<status>, GSI2SK: INVOICE#<invoice_id>

    13. Get overdue invoices:
        GSI3PK: OVERDUE, GSI3SK: <due_date>#<invoice_id>

    14. Get risk assessments for customer:
        PK: CUSTOMER#<customer_id>, SK: RISK#

    15. Get AI insights for company:
        PK: COMPANY#<company_id>, SK: INSIGHT#

    16. Get receipts for invoice:
        GSI1PK: INVOICE#<invoice_id>, GSI1SK: RECEIPT#

    17. Get company settings:
        PK: COMPANY#<company_id>, SK: SETTING#

    18. Get API token info:
        PK: COMPANY#<company_id>, SK: TOKEN#METADATA

    19. Get token usage history:
        PK: COMPANY#<company_id>, SK: TOKEN#USAGE#<timestamp>

    20. Get communications for customer:
        GSI1PK: CUSTOMER#<customer_id>, GSI1SK: COMM#
    """
    pass


def create_key_structure(entity_type: str, entity_id: str, sub_type: str = "METADATA") -> Dict[str, str]:
    """
    Create consistent key structure for DynamoDB items

    Args:
        entity_type: Type of entity (USER, COMPANY, INVOICE, etc.)
        entity_id: Unique identifier for the entity
        sub_type: Sub-type for sort key (METADATA, ITEM, etc.)

    Returns:
        Dictionary with PK and SK values
    """
    return {
        "PK": f"{entity_type}#{entity_id}",
        "SK": sub_type
    }


def create_gsi_keys(item: Dict[str, Any], entity_type: str) -> Dict[str, Any]:
    """
    Add GSI keys to an item based on entity type

    Args:
        item: The DynamoDB item
        entity_type: Type of entity

    Returns:
        Item with GSI keys added
    """
    # Add GSI keys based on entity type
    if entity_type == EntityTypes.USER and "email" in item:
        item["GSI4PK"] = f"EMAIL#{item['email'].lower()}"
        item["GSI4SK"] = "USER"

    elif entity_type == EntityTypes.INVOICE:
        # For querying by customer
        if "customer_id" in item:
            item["GSI1PK"] = f"CUSTOMER#{item['customer_id']}"
            item["GSI1SK"] = f"INVOICE#{item.get('issue_date', '')}#{item['id']}"

        # For querying by status
        if "status" in item:
            item["GSI2PK"] = f"STATUS#{item['status']}"
            item["GSI2SK"] = f"INVOICE#{item['id']}"

        # For querying by company
        if "company_id" in item:
            item["GSI5PK"] = f"COMPANY#{item['company_id']}"
            item["GSI5SK"] = f"INVOICE#{item.get('issue_date', '')}#{item['id']}"

        # For overdue tracking
        if "due_date" in item and item.get("status") not in ["paid", "cancelled"]:
            item["GSI3PK"] = "OVERDUE"
            item["GSI3SK"] = f"{item['due_date']}#{item['id']}"

    elif entity_type == EntityTypes.CUSTOMER:
        # For querying customers by company
        if "company_id" in item:
            item["GSI5PK"] = f"COMPANY#{item['company_id']}"
            item["GSI5SK"] = f"CUSTOMER#{item.get('customer_name', '')}#{item['id']}"

    elif entity_type == EntityTypes.RISK_ASSESSMENT:
        # For querying risk assessments
        if "customer_id" in item:
            item["GSI1PK"] = f"CUSTOMER#{item['customer_id']}"
            item["GSI1SK"] = f"RISK#{item.get('created_at', '')}#{item['id']}"

        if "risk_level" in item:
            item["GSI2PK"] = f"RISK_LEVEL#{item['risk_level']}"
            item["GSI2SK"] = f"{item.get('created_at', '')}#{item['id']}"

    elif entity_type == EntityTypes.USER_COMPANY:
        # For bi-directional queries
        if "user_id" in item and "company_id" in item:
            item["GSI1PK"] = f"USER#{item['user_id']}"
            item["GSI1SK"] = f"COMPANY#{item['company_id']}"
            item["GSI5PK"] = f"COMPANY#{item['company_id']}"
            item["GSI5SK"] = f"USER#{item['user_id']}"

    return item