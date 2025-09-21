"""Main FastAPI application entry point"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
import structlog

from app.core.config import settings
from app.core.logging import setup_logging, LoggingMiddleware
from app.core.exceptions import setup_exception_handlers
from app.api.v1.router import api_router
from app.dynamodb.client import dynamodb_client
from app.services.aws.event_bridge import EventBridgeService
from app.services.cache import CacheService
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.error_handler import ErrorHandlerMiddleware


# Configure structured logging
setup_logging()
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting application", app_name=settings.APP_NAME, env=settings.APP_ENV)

    # Initialize DynamoDB
    await dynamodb_client.initialize()

    # Initialize cache
    cache_service = CacheService()
    await cache_service.initialize()

    # Initialize AWS services
    event_bridge = EventBridgeService()
    await event_bridge.initialize()

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close DynamoDB connections
    await dynamodb_client.close()

    # Close cache connections
    await cache_service.close()

    # Cleanup AWS services
    await event_bridge.close()

    logger.info("Application shutdown complete")


def create_application() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.API_VERSION,
        docs_url=f"/api/{settings.API_VERSION}/docs" if settings.DEBUG else None,
        redoc_url=f"/api/{settings.API_VERSION}/redoc" if settings.DEBUG else None,
        openapi_url=f"/api/{settings.API_VERSION}/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Middleware - Order matters!
    # 1. Trusted Host (Security)
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*.billingintelligence.com", "localhost"]
        )

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Rate Limiting
    app.add_middleware(RateLimitMiddleware)

    # 4. Error Handling
    app.add_middleware(ErrorHandlerMiddleware)

    # 5. Request Logging
    app.add_middleware(LoggingMiddleware)

    # Setup exception handlers
    setup_exception_handlers(app)

    # Include API routers
    app.include_router(
        api_router,
        prefix=f"/api/{settings.API_VERSION}"
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.API_VERSION,
            "environment": settings.APP_ENV
        }

    @app.get("/")
    async def root():
        return {
            "message": "AWS Billing Intelligence Backend API",
            "version": settings.API_VERSION,
            "docs": f"/api/{settings.API_VERSION}/docs"
        }

    return app


app = create_application()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None  # We use structlog instead
    )