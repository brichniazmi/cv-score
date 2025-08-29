# app/db.py
import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# Use Render's DATABASE_URL at runtime. Keep psycopg2 driver prefix.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/cvscore",
)

# Create engine & session factory
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)

# Declarative base for models
Base = declarative_base()

# FastAPI dependency
# IMPORTANT: do NOT decorate with @contextmanager. It must be a generator that yields the Session.
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
