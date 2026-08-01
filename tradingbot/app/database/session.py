"""Database session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator

from app.core.config import settings
from app.models.base import Base

def get_database_url() -> str:
    """Get the database URL with proper configuration."""
    db_url = settings.DATABASE_URL
    if not db_url:
        # SQLite fallback for development
        import os
        db_dir = os.path.abspath(settings.DATA_DIR)
        os.makedirs(db_dir, exist_ok=True)
        sqlite_path = os.path.join(db_dir, "tradingbot.db")
        db_url = f"sqlite:///{sqlite_path}"
        print("⚠️  Using SQLite fallback - PostgreSQL recommended for production")
    else:
        # Normalize postgres:// to postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url

# Create engine
db_url = get_database_url()
is_sqlite = db_url.startswith("sqlite")

if is_sqlite:
    # SQLite configuration
    engine = create_engine(
        db_url,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
            "timeout": 20
        },
        echo=False
    )
else:
    # PostgreSQL configuration
    engine = create_engine(
        db_url,
        pool_size=15,
        max_overflow=25,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False  # Set to True for SQL debugging
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_tables():
    """Create all database tables."""
    import app.models.trading  # Ensure models are registered
    Base.metadata.create_all(bind=engine)
    
def drop_tables():
    """Drop all database tables - USE WITH CAUTION."""
    Base.metadata.drop_all(bind=engine)

def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Initialize tables on import
try:
    create_tables()
    print("Database tables initialized successfully")
except Exception as e:
    print(f"Failed to initialize database tables: {e}")