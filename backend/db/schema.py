from sqlalchemy import create_engine, text
from .models import Base

def init_db(db_url: str):
    """
    Initializes the database schema.
    Enables PostGIS extension if it's a PostgreSQL database.
    """
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Enable PostGIS extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        conn.commit()

    # Create all tables defined in models.py
    Base.metadata.create_all(engine)
    return engine
