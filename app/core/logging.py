"""Structured logging configuration"""

import structlog
import logging
import sys
import json
from typing import Dict, Any
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import uuid

from app.core.config import settings


def setup_logging():
    """Configure structured logging for the application"""

    # Configure structlog processors
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.contextvars.merge_contextvars,
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME
            ]
        ),
    ]

    if settings.LOG_FORMAT == "json":
        # JSON output for production
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    handler = logging.StreamHandler(sys.stdout)

    # Use ProcessorFormatter to format standard logs through structlog
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Quiet noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses"""

    async def dispatch(self, request: Request, call_next):
        # Generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Add request ID to context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Log request
        logger = structlog.get_logger()

        start_time = time.time()

        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
            client_host=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            endpoint=f"{request.method} {request.url.path}"
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate request duration
            duration = time.time() - start_time

            # Log response
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration=round(duration, 3),
                endpoint=f"{request.method} {request.url.path}"
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration = time.time() - start_time

            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                duration=round(duration, 3),
                exception_type=type(e).__name__,
                exception_message=str(e),
                endpoint=f"{request.method} {request.url.path}"
            )
            raise


class MetricsLogger:
    """Logger for application metrics"""

    def __init__(self):
        self.logger = structlog.get_logger("metrics")

    def log_business_metric(
        self,
        metric_name: str,
        value: Any,
        tags: Dict[str, str] = None,
        unit: str = None
    ):
        """Log a business metric"""
        self.logger.info(
            "business_metric",
            metric_name=metric_name,
            value=value,
            tags=tags or {},
            unit=unit,
            timestamp=datetime.utcnow().isoformat()
        )

    def log_performance_metric(
        self,
        operation: str,
        duration: float,
        success: bool,
        tags: Dict[str, str] = None
    ):
        """Log a performance metric"""
        self.logger.info(
            "performance_metric",
            operation=operation,
            duration=round(duration, 3),
            success=success,
            tags=tags or {},
            timestamp=datetime.utcnow().isoformat()
        )

    def log_aws_api_call(
        self,
        service: str,
        operation: str,
        duration: float,
        success: bool,
        error_code: str = None
    ):
        """Log AWS API call metrics"""
        self.logger.info(
            "aws_api_call",
            service=service,
            operation=operation,
            duration=round(duration, 3),
            success=success,
            error_code=error_code,
            timestamp=datetime.utcnow().isoformat()
        )

    def log_cache_operation(
        self,
        operation: str,
        key: str,
        hit: bool,
        duration: float
    ):
        """Log cache operation metrics"""
        self.logger.info(
            "cache_operation",
            operation=operation,
            key=key,
            cache_hit=hit,
            duration=round(duration, 3),
            timestamp=datetime.utcnow().isoformat()
        )


# Global metrics logger instance
metrics_logger = MetricsLogger()