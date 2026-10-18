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

def search_providers(session, specialty=None, plan_id=None, lat=None, lon=None, radius_meters=5000, sort_by=None):
    """
    Searches for providers based on specialty, insurance plan, and location.
    Supports sorting by 'rating' and 'distance'.
    """
    query = session.query(Provider)

    if specialty:
        query = query.filter(Provider.specialty == specialty)

    if plan_id:
        query = query.join(provider_networks).filter(
            provider_networks.c.plan_id == plan_id,
            provider_networks.c.is_in_network == True
        )

    if lat is not None and lon is not None:
        # PostGIS functions (ST_DWithin, ST_GeomFromText) are not available in SQLite.
        # For unit tests using SQLite, we skip the geospatial filter.
        if session.bind.dialect.name != 'sqlite':
            point = func.ST_GeomFromText(f'POINT({lon} {lat})', 4326)
            query = query.filter(func.ST_DWithin(Provider.location, point, radius_meters))

    if sort_by == 'rating':
        query = query.order_by(Provider.rating.desc())
    elif sort_by == 'distance' and lat is not None and lon is not None:
        if session.bind.dialect.name != 'sqlite':
            point = func.ST_GeomFromText(f'POINT({lon} {lat})', 4326)
            query = query.order_by(func.ST_Distance(Provider.location, point))

    return query.all()
