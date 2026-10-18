from sqlalchemy import create_engine, text, func
from sqlalchemy.orm import sessionmaker, scoped_session
from .models import Base, Provider, InsuranceCarrier, NetworkPlan, provider_networks

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

    if _engine.dialect.name == 'postgresql':
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

def search_providers(session, specialty=None, plan_id=None, lat=None, lon=None, radius_meters=5000):
    """
    Searches for providers based on specialty, insurance plan, and location.
    """
    query = session.query(Provider)

    if specialty:
        query = query.filter(Provider.specialty == specialty)

    if plan_id:
        query = query.join(Provider.plans).filter(NetworkPlan.id == plan_id)

    if lat is not None and lon is not None:
        # Use ST_DWithin for geospatial radius search
        # point is created from lon/lat
        point = func.ST_GeomFromText(f'POINT({lon} {lat})', 4326)
        query = query.filter(func.ST_DWithin(Provider.location, point, radius_meters))

    return query.all()
