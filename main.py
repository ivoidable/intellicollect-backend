"""Main FastAPI application entry point"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
import structlog

from core.config import settings
from core.logging import setup_logging, LoggingMiddleware
from core.exceptions import setup_exception_handlers
from api.router import api_router
from dynamodb.client import dynamodb_client
from services.aws.event_bridge import EventBridgeService
# from services.cache import CacheService  # TODO: Create cache service
# from middleware.rate_limit import RateLimitMiddleware  # TODO: Create rate limit middleware
# from middleware.error_handler import ErrorHandlerMiddleware  # TODO: Create error handler middleware


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
    # cache_service = CacheService()  # TODO: Implement cache service
    # await cache_service.initialize()

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
    # await cache_service.close()  # TODO: Implement cache service

    # Cleanup AWS services
    await event_bridge.close()

    logger.info("Application shutdown complete")


def create_application() -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.API_VERSION,
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Middleware - Order matters!
    # 1. Trusted Host (Security)
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"]
        )

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Rate Limiting
    # app.add_middleware(RateLimitMiddleware)  # TODO: Implement rate limiting middleware

    # 4. Error Handling
    # app.add_middleware(ErrorHandlerMiddleware)  # TODO: Implement error handler middleware

    # 5. Request Logging
    app.add_middleware(LoggingMiddleware)

    # Setup exception handlers
    setup_exception_handlers(app)

    # Include API routers
    app.include_router(
        api_router,
        prefix="/api"
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
            "docs": "/api/docs"
        }

    return app


app = create_application()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_config=None  # We use structlog instead
    )
