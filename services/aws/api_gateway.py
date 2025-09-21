"""AWS API Gateway service for interacting with Lambda functions via API Gateway"""

import asyncio
import json
from typing import Dict, Any, Optional
import structlog
import aiohttp
from datetime import datetime

from core.config import settings
from services.aws.base import AWSServiceBase, aws_error_handler

logger = structlog.get_logger()


class AWSAPIGatewayService(AWSServiceBase):
    """Service for making requests to AWS API Gateway endpoints"""

    def __init__(self):
        super().__init__("apigateway")
        self.base_url = settings.AWS_API_GATEWAY_BASE_URL
        self.api_key = settings.AWS_API_KEY
        self.session = None

    async def initialize(self):
        """Initialize the HTTP session"""
        if not self.base_url:
            raise ValueError("AWS_API_GATEWAY_BASE_URL must be configured")
        if not self.api_key:
            raise ValueError("AWS_API_KEY must be configured")

        # Create aiohttp session with timeout
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json"
            }
        )
        self._initialized = True
        logger.info("AWS API Gateway service initialized", base_url=self.base_url)

    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
        await super().close()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to API Gateway endpoint"""
        self.ensure_initialized()

        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        try:
            async with self.session.request(
                method,
                url,
                json=data,
                headers={"x-api-key": self.api_key}
            ) as response:
                response_text = await response.text()

                logger.info(
                    "API Gateway request completed",
                    method=method,
                    url=url,
                    status=response.status,
                    response_size=len(response_text)
                )

                if response.status >= 400:
                    logger.error(
                        "API Gateway request failed",
                        method=method,
                        url=url,
                        status=response.status,
                        response=response_text
                    )
                    raise Exception(f"API Gateway request failed: {response.status} - {response_text}")

                # Parse response JSON
                try:
                    response_data = json.loads(response_text)

                    # Handle Lambda response format where body is a JSON string
                    if isinstance(response_data, dict) and "body" in response_data:
                        if isinstance(response_data["body"], str):
                            try:
                                response_data["body"] = json.loads(response_data["body"])
                            except json.JSONDecodeError:
                                # Keep as string if not valid JSON
                                pass

                    return response_data
                except json.JSONDecodeError:
                    logger.error(
                        "Failed to parse API Gateway response as JSON",
                        response=response_text
                    )
                    raise Exception(f"Invalid JSON response: {response_text}")

        except aiohttp.ClientError as e:
            logger.error(
                "HTTP client error",
                method=method,
                url=url,
                error=str(e)
            )
            raise Exception(f"HTTP request failed: {str(e)}")

    @aws_error_handler
    async def generate_payment_plan(
        self,
        customer_id: str,
        request_type: str,
        total_amount: Optional[float] = None,
        requested_months: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate payment plan via API Gateway"""

        payload = {
            "detail": {
                "customer_id": customer_id,
                "request_type": request_type
            }
        }

        if total_amount is not None:
            payload["detail"]["total_amount"] = total_amount
        if requested_months is not None:
            payload["detail"]["requested_months"] = requested_months

        logger.info(
            "Generating payment plan",
            customer_id=customer_id,
            request_type=request_type,
            total_amount=total_amount,
            requested_months=requested_months
        )

        response = await self._make_request("POST", "generate-payment-plan", payload)

        # Extract body from Lambda response format
        if isinstance(response, dict) and "body" in response:
            response_body = response["body"]
            if isinstance(response_body, dict):
                return response_body
            else:
                return {"raw_response": response}

        return response

    @aws_error_handler
    async def process_receipt(
        self,
        receipt_image_key: str,
        customer_id: str,
        reference_invoice: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process receipt via API Gateway"""

        payload = {
            "detail": {
                "receipt_image_key": receipt_image_key,
                "customer_id": customer_id
            }
        }

        if reference_invoice:
            payload["detail"]["reference_invoice"] = reference_invoice

        logger.info(
            "Processing receipt",
            receipt_image_key=receipt_image_key,
            customer_id=customer_id,
            reference_invoice=reference_invoice
        )

        response = await self._make_request("POST", "process-receipt", payload)

        # Extract body from Lambda response format
        if isinstance(response, dict) and "body" in response:
            response_body = response["body"]
            if isinstance(response_body, dict):
                return response_body
            else:
                return {"raw_response": response}

        return response

    @aws_error_handler
    async def assess_risk(
        self,
        customer_id: str,
        invoice_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess customer risk via API Gateway"""

        payload = {
            "detail": {
                "customer_id": customer_id,
                "invoice_data": invoice_data
            }
        }

        logger.info(
            "Assessing risk",
            customer_id=customer_id,
            invoice_amount=invoice_data.get("amount")
        )

        response = await self._make_request("POST", "risk-assessment", payload)

        # Extract body from Lambda response format
        if isinstance(response, dict) and "body" in response:
            response_body = response["body"]
            if isinstance(response_body, dict):
                return response_body
            else:
                return {"raw_response": response}

        return response

    async def check_service_health(self) -> bool:
        """Check if the API Gateway service is accessible"""
        try:
            self.ensure_initialized()

            # Make a simple request to check connectivity
            # Using OPTIONS request which should be available on all endpoints
            url = f"{self.base_url.rstrip('/')}/generate-payment-plan"
            async with self.session.request(
                "OPTIONS",
                url,
                headers={"x-api-key": self.api_key}
            ) as response:
                return response.status < 500

        except Exception as e:
            logger.error("API Gateway health check failed", error=str(e))
            return False

    def get_service_metrics(self) -> Dict[str, Any]:
        """Get service usage metrics"""
        base_metrics = super().get_service_metrics()
        base_metrics.update({
            "base_url": self.base_url,
            "has_api_key": bool(self.api_key),
            "session_active": self.session is not None and not self.session.closed
        })
        return base_metrics


# Global service instance
api_gateway_service = AWSAPIGatewayService()