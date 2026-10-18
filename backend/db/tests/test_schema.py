import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.schema import init_db, get_db_session, Provider, InsuranceCarrier, NetworkPlan
from backend.db.encryption import encrypt_phi, decrypt_phi
from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point

# Use SQLite for basic schema tests, but note that PostGIS features
# won't be fully available without a real Postgres.
# For unit tests in this environment, we will mock the geospatial part
# or use a compatible approach.
TEST_DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db(TEST_DB_URL)

@pytest.fixture
def db_session():
    session = get_db_session()
    yield session
    session.rollback()
    session.close()

def test_insurance_carrier_creation(db_session):
    carrier = InsuranceCarrier(name="BlueCross BlueShield", payer_id="BCBS001")
    db_session.add(carrier)
    db_session.commit()

    carrier_from_db = db_session.query(InsuranceCarrier).filter_by(payer_id="BCBS001").first()
    assert carrier_from_db is not None
    assert carrier_from_db.name == "BlueCross BlueShield"

def test_network_plan_creation(db_session):
    carrier = InsuranceCarrier(name="Aetna", payer_id="AET001")
    db_session.add(carrier)
    db_session.commit()

    plan = NetworkPlan(carrier_id=carrier.id, plan_name="Aetna PPO Gold", plan_type="PPO", tier="Gold")
    db_session.add(plan)
    db_session.commit()

    plan_from_db = db_session.query(NetworkPlan).filter_by(plan_name="Aetna PPO Gold").first()
    assert plan_from_db is not None
    assert plan_from_db.carrier_id == carrier.id

def test_provider_creation_and_network_mapping(db_session):
    carrier = InsuranceCarrier(name="Cigna", payer_id="CIG001")
    db_session.add(carrier)
    db_session.commit()

    plan = NetworkPlan(carrier_id=carrier.id, plan_name="Cigna Open Access", plan_type="PPO")
    db_session.add(plan)
    db_session.commit()

    # In SQLite, Geometry is handled as a string/blob by geoalchemy2
    provider = Provider(
        npi="1234567890",
        name="Dr. Smith",
        specialty="Cardiology",
        location=WKTElement('POINT(-122.4194 37.7749)') # SF
    )
    db_session.add(provider)
    db_session.commit()

    # Map provider to plan
    from backend.db.models import provider_networks
    db_session.execute(
        provider_networks.insert().values(provider_id=provider.id, plan_id=plan.id, is_in_network=True)
    )
    db_session.commit()

    mapped_provider = db_session.query(Provider).join(Provider.plans).filter(NetworkPlan.id == plan.id).first()
    assert mapped_provider is not None
    assert mapped_provider.name == "Dr. Smith"

def test_phi_encryption_decryption():
    original_data = "Patient sensitive info"
    encrypted = encrypt_phi(original_data)
    assert encrypted != original_data
    assert decrypt_phi(encrypted) == original_data

def test_phi_column_automation(db_session):
    # Note: To test PHIColumn, we'd need a model with a PHIColumn.
    # Let's add a temporary model for this test.
    from sqlalchemy import Column, Integer, String
    from backend.db.models import Base, PHIColumn

    class PatientRecord(Base):
        __tablename__ = 'patient_records'
        id = Column(Integer, primary_key=True)
        phi_data = Column(PHIColumn)

    Base.metadata.create_all(db_session.bind)

    record = PatientRecord(phi_data="Secret Diagnosis")
    db_session.add(record)
    db_session.commit()

    # Verify it's encrypted in the DB
    raw_data = db_session.execute(
        text("SELECT phi_data FROM patient_records WHERE id = :id"),
        {"id": record.id}
    ).scalar()
    assert raw_data != "Secret Diagnosis"

    # Verify it's decrypted when accessed via SQLAlchemy model
    record_from_db = db_session.query(PatientRecord).first()
    assert record_from_db.phi_data == "Secret Diagnosis"
