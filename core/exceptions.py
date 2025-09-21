"""Custom exceptions and error handlers"""

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Any, Dict, Optional
import structlog
import traceback

logger = structlog.get_logger()


class BillingIntelligenceError(Exception):
    """Base exception for application errors"""
    def __init__(self, message: str, code: str = "UNKNOWN_ERROR", details: Optional[Dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class DatabaseError(BillingIntelligenceError):
    """Database operation errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "DATABASE_ERROR", details)


class AWSServiceError(BillingIntelligenceError):
    """AWS service integration errors"""
    def __init__(self, message: str, service: str, details: Optional[Dict] = None):
        details = details or {}
        details['service'] = service
        super().__init__(message, "AWS_SERVICE_ERROR", details)


class RiskAssessmentError(BillingIntelligenceError):
    """Risk assessment errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "RISK_ASSESSMENT_ERROR", details)


class CommunicationError(BillingIntelligenceError):
    """Communication service errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "COMMUNICATION_ERROR", details)


class PaymentProcessingError(BillingIntelligenceError):
    """Payment processing errors"""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message, "PAYMENT_ERROR", details)


class RateLimitError(BillingIntelligenceError):
    """Rate limiting errors"""
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict] = None):
        super().__init__(message, "RATE_LIMIT_ERROR", details)


class AuthenticationError(BillingIntelligenceError):
    """Authentication errors"""
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(message, "AUTH_ERROR", details)


class AuthorizationError(BillingIntelligenceError):
    """Authorization errors"""
    def __init__(self, message: str = "Insufficient permissions", details: Optional[Dict] = None):
        super().__init__(message, "AUTHZ_ERROR", details)


def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[Dict] = None,
    request_id: Optional[str] = None
) -> JSONResponse:
    """Create standardized error response"""
    content = {
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {}
        }
    }

    if request_id:
        content["error"]["request_id"] = request_id

    return JSONResponse(
        status_code=status_code,
        content=content
    )


async def billing_intelligence_error_handler(request: Request, exc: BillingIntelligenceError) -> JSONResponse:
    """Handler for application-specific errors"""
    logger.error(
        "Application error",
        error_code=exc.code,
        error_message=exc.message,
        error_details=exc.details,
        path=request.url.path,
        method=request.method
    )

    # Map error codes to HTTP status codes
    status_map = {
        "DATABASE_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "AWS_SERVICE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
        "RISK_ASSESSMENT_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "COMMUNICATION_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "PAYMENT_ERROR": status.HTTP_402_PAYMENT_REQUIRED,
        "RATE_LIMIT_ERROR": status.HTTP_429_TOO_MANY_REQUESTS,
        "AUTH_ERROR": status.HTTP_401_UNAUTHORIZED,
        "AUTHZ_ERROR": status.HTTP_403_FORBIDDEN,
        "UNKNOWN_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR
    }

    return create_error_response(
        error_code=exc.code,
        message=exc.message,
        status_code=status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR),
        details=exc.details,
        request_id=request.headers.get("X-Request-ID")
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handler for HTTP exceptions"""
    logger.warning(
        "HTTP exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method
    )

    return create_error_response(
        error_code=f"HTTP_{exc.status_code}",
        message=exc.detail or "An error occurred",
        status_code=exc.status_code,
        request_id=request.headers.get("X-Request-ID")
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for validation errors"""
    logger.warning(
        "Validation error",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method
    )

    # Format validation errors
    formatted_errors = []
    for error in exc.errors():
        formatted_errors.append({
            "field": ".".join(str(loc) for loc in error["loc"][1:]),
            "message": error["msg"],
            "type": error["type"]
        })

    return create_error_response(
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": formatted_errors},
        request_id=request.headers.get("X-Request-ID")
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for unhandled exceptions"""
    logger.error(
        "Unhandled exception",
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        traceback=traceback.format_exc(),
        path=request.url.path,
        method=request.method
    )

    # Don't expose internal errors in production
    from app.core.config import settings
    if settings.DEBUG:
        details = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc().split("\n")
        }
    else:
        details = {}

    return create_error_response(
        error_code="INTERNAL_ERROR",
        message="An internal error occurred",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details=details,
        request_id=request.headers.get("X-Request-ID")
    )


def setup_exception_handlers(app: FastAPI):
    """Setup all exception handlers for the application"""
    app.add_exception_handler(BillingIntelligenceError, billing_intelligence_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)