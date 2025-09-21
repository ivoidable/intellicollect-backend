"""Base AWS service class with common functionality"""

import boto3
from botocore.exceptions import ClientError
from typing import Optional, Dict, Any
import structlog
from functools import wraps
import asyncio
import time

from core.config import settings

logger = structlog.get_logger()


def aws_error_handler(func):
    """Decorator to handle AWS API errors"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(
                "AWS API error",
                service=args[0].__class__.__name__,
                operation=func.__name__,
                error_code=error_code,
                error_message=error_message
            )

            # Handle specific error codes
            if error_code == 'ThrottlingException':
                # Implement exponential backoff
                await asyncio.sleep(2 ** kwargs.get('retry_count', 1))
                if kwargs.get('retry_count', 0) < 3:
                    kwargs['retry_count'] = kwargs.get('retry_count', 0) + 1
                    return await wrapper(*args, **kwargs)

            raise
        except Exception as e:
            logger.error(
                "Unexpected AWS service error",
                service=args[0].__class__.__name__,
                operation=func.__name__,
                error=str(e)
            )
            raise
    return wrapper


class AWSServiceBase:
    """Base class for AWS service integrations"""

    def __init__(self, service_name: str):
        self.service_name = service_name
        self.region = settings.AWS_REGION
        self.client = None
        self.resource = None
        self._initialized = False

    async def initialize(self):
        """Initialize AWS service client"""
        try:
            # Create session with credentials
            session = boto3.Session(
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=self.region
            )

            # Create client
            self.client = session.client(self.service_name)

            # Some services also have resource interfaces
            if self.service_name in ['s3', 'dynamodb', 'sqs', 'sns']:
                self.resource = session.resource(self.service_name)

            self._initialized = True
            logger.info(f"AWS {self.service_name} service initialized")

        except Exception as e:
            logger.error(f"Failed to initialize AWS {self.service_name}", error=str(e))
            raise

    async def close(self):
        """Close AWS service connections"""
        # boto3 handles connection pooling internally
        self._initialized = False
        logger.info(f"AWS {self.service_name} service closed")

    def ensure_initialized(self):
        """Ensure service is initialized before use"""
        if not self._initialized:
            raise RuntimeError(f"AWS {self.service_name} service not initialized")

    @aws_error_handler
    async def execute_with_retry(
        self,
        operation: str,
        params: Dict[str, Any],
        max_retries: int = 3,
        backoff_base: int = 2
    ):
        """Execute AWS operation with exponential backoff retry"""
        self.ensure_initialized()

        for attempt in range(max_retries):
            try:
                # Get the operation method
                operation_func = getattr(self.client, operation)

                # Execute in thread pool since boto3 is synchronous
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: operation_func(**params)
                )
                return result

            except ClientError as e:
                error_code = e.response['Error']['Code']

                # Don't retry on certain errors
                if error_code in ['ValidationException', 'InvalidParameterValue']:
                    raise

                if attempt < max_retries - 1:
                    wait_time = backoff_base ** attempt
                    logger.warning(
                        f"AWS operation failed, retrying",
                        operation=operation,
                        attempt=attempt + 1,
                        wait_time=wait_time,
                        error=error_code
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

    async def check_service_health(self) -> bool:
        """Check if the AWS service is accessible"""
        try:
            self.ensure_initialized()

            # Different health check methods for different services
            if self.service_name == 's3':
                await self.execute_with_retry('list_buckets', {})
            elif self.service_name == 'sqs':
                await self.execute_with_retry('list_queues', {})
            elif self.service_name == 'sns':
                await self.execute_with_retry('list_topics', {})
            elif self.service_name == 'eventbridge':
                await self.execute_with_retry('list_event_buses', {})
            else:
                # Generic describe operation
                await self.execute_with_retry('describe_limits', {})

            return True
        except:
            return False

    def get_service_metrics(self) -> Dict[str, Any]:
        """Get service usage metrics"""
        # This would integrate with CloudWatch in production
        return {
            'service': self.service_name,
            'region': self.region,
            'initialized': self._initialized,
            'health': 'healthy' if self._initialized else 'unavailable'
        }