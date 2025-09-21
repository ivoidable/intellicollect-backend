"""API v1 main router"""

from fastapi import APIRouter

from app.api.v1.endpoints import customers, invoices, payments, communications, risk, analytics, webhooks

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(
    customers.router,
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
    communications.router,
    prefix="/communications",
    tags=["communications"]
)

api_router.include_router(
    risk.router,
    prefix="/risk",
    tags=["risk"]
)

api_router.include_router(
    analytics.router,
    prefix="/analytics",
    tags=["analytics"]
)

api_router.include_router(
    webhooks.router,
    prefix="/webhooks",
    tags=["webhooks"]
)