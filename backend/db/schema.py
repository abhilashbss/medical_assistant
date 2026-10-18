from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, scoped_session
from .models import Base, Provider, InsuranceCarrier, NetworkPlan

# Global engine and session factory
_engine = None
_SessionFactory = None

def init_db(db_url: str):
    """
    Initializes the database schema.
    Enables PostGIS extension if it's a PostgreSQL database.
    """
    global _engine, _SessionFactory
    _engine = create_engine(db_url)
    _SessionFactory = scoped_session(sessionmaker(bind=_engine))

    with _engine.connect() as conn:
        # Enable PostGIS extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()

    # Create all tables defined in models.py
    Base.metadata.create_all(_engine)
    return _engine

def get_db_session():
    """
    Returns a new database session.
    """
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db(url) first.")
    return _SessionFactory()
