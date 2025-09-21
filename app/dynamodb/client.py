"""DynamoDB Client Service

Manages DynamoDB connections and operations
"""

import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from typing import Dict, Any, List, Optional, Union
import structlog
from decimal import Decimal
import json
from datetime import datetime
import asyncio
from functools import wraps

from app.core.config import settings
from app.dynamodb.tables import TableNames, EntityTypes, GSINames, create_key_structure, create_gsi_keys

logger = structlog.get_logger()


def handle_dynamodb_errors(func):
    """Decorator to handle DynamoDB errors"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']

            logger.error(
                "DynamoDB operation failed",
                operation=func.__name__,
                error_code=error_code,
                error_message=error_message
            )

            if error_code == 'ResourceNotFoundException':
                raise Exception(f"Table not found: {error_message}")
            elif error_code == 'ValidationException':
                raise ValueError(f"Invalid request: {error_message}")
            elif error_code == 'ProvisionedThroughputExceededException':
                # Retry with exponential backoff
                await asyncio.sleep(1)
                return await wrapper(*args, **kwargs)
            else:
                raise
        except Exception as e:
            logger.error(
                "Unexpected DynamoDB error",
                operation=func.__name__,
                error=str(e)
            )
            raise
    return wrapper


class DynamoDBClient:
    """DynamoDB client for database operations"""

    def __init__(self):
        self.region = settings.AWS_REGION
        self.client = None
        self.resource = None
        self.tables = {}
        self._initialized = False

    async def initialize(self):
        """Initialize DynamoDB connections"""
        try:
            # Set environment variables for boto3
            import os
            if settings.AWS_ACCESS_KEY_ID:
                os.environ['AWS_ACCESS_KEY_ID'] = settings.AWS_ACCESS_KEY_ID
            if settings.AWS_SECRET_ACCESS_KEY:
                os.environ['AWS_SECRET_ACCESS_KEY'] = settings.AWS_SECRET_ACCESS_KEY
            if self.region:
                os.environ['AWS_DEFAULT_REGION'] = self.region

            # Create session
            session = boto3.Session(
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=self.region
            )

            # Create client and resource
            self.client = session.client('dynamodb')
            self.resource = session.resource('dynamodb')

            # Get table references
            self.tables = {
                TableNames.MAIN: self.resource.Table(TableNames.MAIN),
                TableNames.AUDIT: self.resource.Table(TableNames.AUDIT),
                TableNames.METRICS: self.resource.Table(TableNames.METRICS)
            }

            # Verify tables exist
            await self._verify_tables()

            self._initialized = True
            logger.info("DynamoDB client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB client", error=str(e))
            raise

    async def _verify_tables(self):
        """Verify that required tables exist"""
        loop = asyncio.get_event_loop()

        for table_name in [TableNames.MAIN, TableNames.AUDIT, TableNames.METRICS]:
            try:
                await loop.run_in_executor(None, lambda: self.client.describe_table(TableName=table_name))
                logger.info(f"Table {table_name} verified")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.warning(f"Table {table_name} not found, creating...")
                    await self._create_table(table_name)
                else:
                    raise

    async def _create_table(self, table_name: str):
        """Create a DynamoDB table if it doesn't exist"""
        # Import table schemas
        from app.dynamodb.tables import MAIN_TABLE_SCHEMA, AUDIT_TABLE_SCHEMA, METRICS_TABLE_SCHEMA

        schemas = {
            TableNames.MAIN: MAIN_TABLE_SCHEMA,
            TableNames.AUDIT: AUDIT_TABLE_SCHEMA,
            TableNames.METRICS: METRICS_TABLE_SCHEMA
        }

        schema = schemas.get(table_name)
        if not schema:
            raise ValueError(f"Unknown table: {table_name}")

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.client.create_table(**schema))

        # Wait for table to be active
        waiter = self.client.get_waiter('table_exists')
        await loop.run_in_executor(None, lambda: waiter.wait(TableName=table_name))

        logger.info(f"Table {table_name} created successfully")

    def ensure_initialized(self):
        """Ensure client is initialized before operations"""
        if not self._initialized:
            raise RuntimeError("DynamoDB client not initialized")

    @handle_dynamodb_errors
    async def put_item(self, table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Put an item into DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        # Add timestamp
        if 'created_at' not in item:
            item['created_at'] = datetime.utcnow().isoformat()
        item['updated_at'] = datetime.utcnow().isoformat()

        # Convert to DynamoDB format
        item = self._convert_to_dynamodb_format(item)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, table.put_item, Item=item)

        logger.info(f"Item added to {table_name}", pk=item.get('PK'), sk=item.get('SK'))
        return item

    @handle_dynamodb_errors
    async def get_item(self, table_name: str, pk: str, sk: str) -> Optional[Dict[str, Any]]:
        """Get a single item from DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            table.get_item,
            Key={'PK': pk, 'SK': sk}
        )

        item = response.get('Item')
        if item:
            item = self._convert_from_dynamodb_format(item)

        return item

    @handle_dynamodb_errors
    async def query(
        self,
        table_name: str,
        key_condition: Union[str, Dict[str, Any]],
        index_name: Optional[str] = None,
        filter_expression: Optional[Any] = None,
        limit: Optional[int] = None,
        last_evaluated_key: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query items from DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        query_params = {}

        # Handle key condition
        if isinstance(key_condition, str):
            query_params['KeyConditionExpression'] = Key('PK').eq(key_condition)
        else:
            query_params['KeyConditionExpression'] = key_condition

        if index_name:
            query_params['IndexName'] = index_name

        if filter_expression:
            query_params['FilterExpression'] = filter_expression

        if limit:
            query_params['Limit'] = limit

        if last_evaluated_key:
            query_params['ExclusiveStartKey'] = last_evaluated_key

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, table.query, **query_params)

        # Convert items from DynamoDB format
        items = [self._convert_from_dynamodb_format(item) for item in response.get('Items', [])]

        return {
            'Items': items,
            'Count': response.get('Count', 0),
            'LastEvaluatedKey': response.get('LastEvaluatedKey')
        }

    @handle_dynamodb_errors
    async def update_item(
        self,
        table_name: str,
        pk: str,
        sk: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an item in DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        # Build update expression
        update_expression = "SET "
        expression_attribute_names = {}
        expression_attribute_values = {}

        for i, (key, value) in enumerate(updates.items()):
            # Handle reserved keywords
            attr_name = f"#{key}"
            attr_value = f":val{i}"

            if i > 0:
                update_expression += ", "
            update_expression += f"{attr_name} = {attr_value}"

            expression_attribute_names[attr_name] = key
            expression_attribute_values[attr_value] = self._convert_value_to_dynamodb(value)

        # Always update the updated_at timestamp
        update_expression += ", #updated_at = :updated_at"
        expression_attribute_names['#updated_at'] = 'updated_at'
        expression_attribute_values[':updated_at'] = datetime.utcnow().isoformat()

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            table.update_item,
            Key={'PK': pk, 'SK': sk},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues='ALL_NEW'
        )

        updated_item = self._convert_from_dynamodb_format(response.get('Attributes', {}))

        logger.info(f"Item updated in {table_name}", pk=pk, sk=sk)
        return updated_item

    @handle_dynamodb_errors
    async def delete_item(self, table_name: str, pk: str, sk: str) -> bool:
        """Delete an item from DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            table.delete_item,
            Key={'PK': pk, 'SK': sk}
        )

        logger.info(f"Item deleted from {table_name}", pk=pk, sk=sk)
        return True

    @handle_dynamodb_errors
    async def batch_write(self, table_name: str, items: List[Dict[str, Any]]) -> int:
        """Batch write items to DynamoDB table"""
        self.ensure_initialized()

        table = self.tables[table_name]

        # Convert items to DynamoDB format
        converted_items = [self._convert_to_dynamodb_format(item) for item in items]

        # DynamoDB batch write supports max 25 items
        written = 0
        for i in range(0, len(converted_items), 25):
            batch = converted_items[i:i+25]

            with table.batch_writer() as batch_writer:
                for item in batch:
                    batch_writer.put_item(Item=item)
                written += len(batch)

        logger.info(f"Batch wrote {written} items to {table_name}")
        return written

    @handle_dynamodb_errors
    async def scan(
        self,
        table_name: str,
        filter_expression: Optional[Any] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Scan table (use sparingly, expensive operation)"""
        self.ensure_initialized()

        table = self.tables[table_name]

        scan_params = {}
        if filter_expression:
            scan_params['FilterExpression'] = filter_expression
        if limit:
            scan_params['Limit'] = limit

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, table.scan, **scan_params)

        items = [self._convert_from_dynamodb_format(item) for item in response.get('Items', [])]

        return items

    def _convert_to_dynamodb_format(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python types to DynamoDB types"""
        converted = {}
        for key, value in item.items():
            converted[key] = self._convert_value_to_dynamodb(value)
        return converted

    def _convert_value_to_dynamodb(self, value: Any) -> Any:
        """Convert a single value to DynamoDB format"""
        if isinstance(value, float):
            return Decimal(str(value))
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._convert_value_to_dynamodb(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._convert_value_to_dynamodb(v) for v in value]
        return value

    def _convert_from_dynamodb_format(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Convert DynamoDB types to Python types"""
        converted = {}
        for key, value in item.items():
            converted[key] = self._convert_value_from_dynamodb(value)
        return converted

    def _convert_value_from_dynamodb(self, value: Any) -> Any:
        """Convert a single value from DynamoDB format"""
        if isinstance(value, Decimal):
            # Convert Decimal to float or int
            if value % 1 == 0:
                return int(value)
            return float(value)
        elif isinstance(value, dict):
            return {k: self._convert_value_from_dynamodb(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._convert_value_from_dynamodb(v) for v in value]
        return value

    async def close(self):
        """Close DynamoDB connections"""
        self._initialized = False
        logger.info("DynamoDB client closed")


# Global DynamoDB client instance
dynamodb_client = DynamoDBClient()