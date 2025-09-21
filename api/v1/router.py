"""API v1 main router"""

from fastapi import APIRouter

from api.v1.endpoints import (
    customers_dynamodb,
    invoices,
    payments,
    risk,
    communications,
    analytics
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    customers_dynamodb.router,
    prefix="/customers",
    tags=["customers"]
)

api_router.include_router(
    invoices.router,
    prefix="/invoices",
    tags=["invoices"]
)

api_router.include_router(
    payments.router,
    prefix="/payments",
    tags=["payments"]
)

api_router.include_router(
    risk.router,
    prefix="/risk",
    tags=["risk"]
)

api_router.include_router(
    communications.router,
    prefix="/communications",
    tags=["communications"]
)

api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"]
)