"""
Database connection setup.
Uses SQLite for local prototype. Replace DB_URL to use PostgreSQL/PostGIS in production.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLite path — relative to project root
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "cashout_forecast.db")
DB_URL = f"sqlite:///{os.path.abspath(DB_PATH)}"

# For PostgreSQL production: DB_URL = "postgresql://user:pass@localhost/cashout_db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a database session and closes it when done."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables if they don't exist."""
    # Import models so SQLAlchemy knows about them
    from backend.database import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print(f"[DB] Database initialized at {DB_PATH}")
