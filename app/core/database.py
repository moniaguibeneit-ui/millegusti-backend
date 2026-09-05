"""SQLAlchemy database setup."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

# Auto-detect: if DATABASE_URL starts with postgresql, use Postgres.
# Otherwise (sqlite or default), use SQLite for local dev.
if settings.DATABASE_URL.startswith("postgresql"):
    # For Neon and other cloud PG providers, ensure SSL is enabled
    url = settings.DATABASE_URL
    if "sslmode" not in url and ("neon" in url or "render" in url or "supabase" in url):
        url = url + ("&sslmode=require" if "?" in url else "?sslmode=require")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=settings.DEBUG,
    )
else:
    # SQLite fallback for local development without Postgres
    engine = create_engine(
        "sqlite:///./millegusti.db",
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
