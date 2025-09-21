"""Application configuration settings"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AWS Billing Intelligence Backend"
    APP_ENV: str = Field(default="development", env="APP_ENV")
    DEBUG: bool = Field(default=True, env="DEBUG")
    API_VERSION: str = Field(default="v1", env="API_VERSION")
    HOST: str = Field(default="0.0.0.0", env="HOST")
    PORT: int = Field(default=8001, env="PORT")

    # Database
    DATABASE_URL: str = Field(default="postgresql://user:pass@localhost/dbname", env="DATABASE_URL")
    DATABASE_URL_ASYNC: str = Field(default="postgresql+asyncpg://user:pass@localhost/dbname", env="DATABASE_URL_ASYNC")
    DATABASE_POOL_SIZE: int = Field(default=10, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=20, env="DATABASE_MAX_OVERFLOW")

    @property
    def database_url_async(self) -> str:
        """Get async database URL"""
        return self.DATABASE_URL_ASYNC

    # DynamoDB Tables
    DYNAMODB_MAIN_TABLE: str = Field(default="BillingIQ-Main", env="DYNAMODB_MAIN_TABLE")
    DYNAMODB_AUDIT_TABLE: str = Field(default="BillingIQ-Audit", env="DYNAMODB_AUDIT_TABLE")
    DYNAMODB_METRICS_TABLE: str = Field(default="BillingIQ-Metrics", env="DYNAMODB_METRICS_TABLE")
    DYNAMODB_CUSTOMERS_TABLE: str = Field(default="BillingCustomers", env="DYNAMODB_CUSTOMERS_TABLE")
    DYNAMODB_INVOICES_TABLE: str = Field(default="BillingInvoices", env="DYNAMODB_INVOICES_TABLE")
    DYNAMODB_RISK_SCORES_TABLE: str = Field(default="RiskScores", env="DYNAMODB_RISK_SCORES_TABLE")
    DYNAMODB_COMMUNICATIONS_TABLE: str = Field(default="Communications", env="DYNAMODB_COMMUNICATIONS_TABLE")
    DYNAMODB_PAYMENT_RECORDS_TABLE: str = Field(default="PaymentRecords", env="DYNAMODB_PAYMENT_RECORDS_TABLE")

    # AWS Configuration
    AWS_REGION: str = Field(default="us-east-1", env="AWS_REGION")
    AWS_DEFAULT_REGION: str = Field(default="us-east-1", env="AWS_DEFAULT_REGION")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, env="AWS_SECRET_ACCESS_KEY")
    AWS_API_KEY: Optional[str] = Field(default=None, env="AWS_API_KEY")

    # AWS API Gateway
    AWS_API_GATEWAY_BASE_URL: Optional[str] = Field(default=None, env="AWS_API_GATEWAY_BASE_URL")

    # AWS Services
    AWS_EVENTBRIDGE_BUS_NAME: str = Field(default="billing-intelligence-bus", env="AWS_EVENTBRIDGE_BUS_NAME")
    EVENT_BUS_NAME: str = Field(default="billing-events", env="EVENT_BUS_NAME")
    AWS_SQS_QUEUE_URL: Optional[str] = Field(default=None, env="AWS_SQS_QUEUE_URL")
    AWS_SNS_TOPIC_ARN: Optional[str] = Field(default=None, env="AWS_SNS_TOPIC_ARN")
    AWS_S3_BUCKET_NAME: str = Field(default="billing-intelligence-documents", env="AWS_S3_BUCKET_NAME")
    AWS_LAMBDA_RISK_ASSESSMENT_FUNCTION: str = Field(default="billing-risk-assessment", env="AWS_LAMBDA_RISK_ASSESSMENT_FUNCTION")
    AWS_LAMBDA_COMMUNICATION_FUNCTION: str = Field(default="billing-auto-communication", env="AWS_LAMBDA_COMMUNICATION_FUNCTION")
    RISK_AGENT_FUNCTION: str = Field(default="risk-agent", env="RISK_AGENT_FUNCTION")
    COMMUNICATION_AGENT_FUNCTION: str = Field(default="communication-agent", env="COMMUNICATION_AGENT_FUNCTION")
    RECEIPT_AGENT_FUNCTION: str = Field(default="receipt-processing-agent", env="RECEIPT_AGENT_FUNCTION")

    # Redis Cache
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_CACHE_TTL: int = Field(default=3600, env="REDIS_CACHE_TTL")

    # Celery
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")

    # Security
    SECRET_KEY: str = Field(default="default-development-secret-key-change-in-production", env="SECRET_KEY")
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, env="REFRESH_TOKEN_EXPIRE_DAYS")

    # CORS
    CORS_ORIGINS: List[str] = Field(default=["*", "https://main.d3jvss61vklbou.amplifyapp.com"], env="CORS_ORIGINS")
    
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")

    # Monitoring
    PROMETHEUS_PORT: int = Field(default=8001, env="PROMETHEUS_PORT")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FORMAT: str = Field(default="json", env="LOG_FORMAT")

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100, env="RATE_LIMIT_REQUESTS")
    RATE_LIMIT_PERIOD: int = Field(default=60, env="RATE_LIMIT_PERIOD")

    # Email
    SMTP_HOST: Optional[str] = Field(default=None, env="SMTP_HOST")
    SMTP_PORT: int = Field(default=587, env="SMTP_PORT")
    SMTP_USER: Optional[str] = Field(default=None, env="SMTP_USER")
    SMTP_PASSWORD: Optional[str] = Field(default=None, env="SMTP_PASSWORD")
    EMAIL_FROM: str = Field(default="noreply@billingintelligence.com", env="EMAIL_FROM")
    VERIFIED_EMAIL: str = Field(default="your-email@gmail.com", env="VERIFIED_EMAIL")

    # Payment Processing
    STRIPE_API_KEY: Optional[str] = Field(default=None, env="STRIPE_API_KEY")
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(default=None, env="STRIPE_WEBHOOK_SECRET")

    # External APIs
    OPENAI_API_KEY: Optional[str] = Field(default=None, env="OPENAI_API_KEY")
    WEBHOOK_SIGNING_SECRET: Optional[str] = Field(default=None, env="WEBHOOK_SIGNING_SECRET")

    @validator("CORS_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
