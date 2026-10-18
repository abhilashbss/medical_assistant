import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from backend.db.schema import init_db, get_db_session
from backend.db.models import Provider, InsuranceCarrier, NetworkPlan, provider_networks
from backend.db.encryption import encrypt_phi, decrypt_phi

# Use an in-memory SQLite database for unit tests.
DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db(DB_URL)
    yield
    # Cleanup is handled by memory DB

@pytest.fixture
def db_session():
    session = get_db_session()
    yield session
    session.rollback()
    session.close()

def test_insurance_carrier_and_plan_creation(db_session):
    """Verify that insurance carriers and plans can be created and linked."""
    carrier = InsuranceCarrier(name="BlueCross", payer_id="BCBS001")
    db_session.add(carrier)
    db_session.commit()

    plan = NetworkPlan(carrier_id=carrier.id, plan_name="PPO Gold", plan_type="PPO", tier="Gold")
    db_session.add(plan)
    db_session.commit()

    assert carrier.id is not None
    assert plan.id is not None
    assert plan.carrier_id == carrier.id

def test_provider_insurance_mapping(db_session):
    """Verify that providers can be mapped to insurance plans with network status."""
    carrier = InsuranceCarrier(name="Aetna", payer_id="AET001")
    db_session.add(carrier)
    db_session.commit()

    plan = NetworkPlan(carrier_id=carrier.id, plan_name="HMO Basic", plan_type="HMO", tier="Basic")
    db_session.add(plan)
    db_session.commit()

    # Use a mock point for SQLite (GeoAlchemy2 supports basic geometry in SQLite but not GIST)
    provider = Provider(
        npi="1234567890",
        name="Dr. Smith",
        specialty="Cardiology",
        location=from_shape(Point(-122.4194, 37.7749), srid=4326)
    )
    db_session.add(provider)
    db_session.commit()

    # Map provider to plan
    provider.plans.append(plan)
    db_session.commit()

    # Verify mapping
    found_provider = db_session.query(Provider).filter_by(npi="1234567890").first()
    assert plan in found_provider.plans

def test_phi_encryption_decryption():
    """Verify that PHI is encrypted and decrypted correctly."""
    original_data = "Patient Social Security Number: 000-00-0000"
    encrypted = encrypt_phi(original_data)

    assert encrypted != original_data
    assert decrypt_phi(encrypted) == original_data

def test_duplicate_npi_constraint(db_session):
    """Verify that duplicate NPIs are not allowed."""
    p1 = Provider(npi="100", name="Dr 1", specialty="S1", location=from_shape(Point(0,0), srid=4326))
    db_session.add(p1)
    db_session.commit()

    p2 = Provider(npi="100", name="Dr 2", specialty="S2", location=from_shape(Point(0,0), srid=4326))
    db_session.add(p2)
    with pytest.raises(Exception): # SQLAlchemy IntegrityError
        db_session.commit()
