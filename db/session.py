"""Database session management"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
import structlog

from core.config import settings
from db.base import Base

logger = structlog.get_logger()

# Create async engine
if settings.APP_ENV == "production":
    engine = create_async_engine(
        settings.database_url_async,
        echo=settings.DEBUG,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        poolclass=QueuePool,
        pool_pre_ping=True,  # Verify connections before using them
    )
else:
    # NullPool doesn't support pool_size and max_overflow
    engine = create_async_engine(
        settings.database_url_async,
        echo=settings.DEBUG,
        poolclass=NullPool,
        pool_pre_ping=True,  # Verify connections before using them
    )

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database (create tables)"""
    try:
        async with engine.begin() as conn:
            # In production, use Alembic migrations instead
            if settings.APP_ENV == "development":
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables created successfully")
            else:
                logger.info("Skipping table creation in production - use migrations")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")