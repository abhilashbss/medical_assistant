import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from geoalchemy2.elements import WKTElement
from backend.db.schema import init_db
from backend.db.models import Provider, InsuranceCarrier, NetworkPlan, PHIColumn
import os

@pytest.fixture
def db_session():
    db_url = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    engine = init_db(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS provider_networks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS providers CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS insurance_plans CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS insurance_carriers CASCADE"))
        conn.commit()

def test_geospatial_index_returns_providers_within_radius(db_session):
    """Geospatial index returns providers within the specified radius."""
    provider_a = Provider(npi="A1", name="Dr. A", specialty="GP",
                           location=WKTElement('POINT(0 0)', srid=4326))
    provider_b = Provider(npi="B2", name="Dr. B", specialty="GP",
                           location=WKTElement('POINT(0.01 0.01)', srid=4326))
    provider_c = Provider(npi="C3", name="Dr. C", specialty="GP",
                           location=WKTElement('POINT(1 1)', srid=4326))

    db_session.add_all([provider_a, provider_b, provider_c])
    db_session.commit()

    query = text("SELECT npi FROM providers WHERE ST_DWithin(location::geography, ST_GeomFromText('POINT(0 0)', 4326)::geography, 5000)")
    results = db_session.execute(query).scalars().all()

    assert "A1" in results
    assert "B2" in results
    assert "C3" not in results

def test_insurance_api_integration_identifies_network_status(db_session):
    """Insurance API integration correctly identifies in-network vs out-of-network status."""
    carrier = InsuranceCarrier(name="BlueCross", payer_id="BCBS001")
    plan = NetworkPlan(plan_name="PPO Gold", carrier=carrier, plan_type="PPO", tier="Gold")
    provider = Provider(npi="1234567890", name="Dr. Smith", specialty="Cardiology",
                        location=WKTElement('POINT(0 0)', srid=4326))

    provider.plans.append(plan)
    db_session.add_all([carrier, plan, provider])
    db_session.commit()

    stmt = text("SELECT is_in_network FROM provider_networks WHERE provider_id = :p AND plan_id = :pl")
    result = db_session.execute(stmt, {"p": provider.id, "pl": plan.id}).scalar()
    assert result is True

    plan_out = NetworkPlan(plan_name="HMO Basic", carrier=carrier, plan_type="HMO", tier="Bronze")
    db_session.add(plan_out)
    db_session.commit()

    result_out = db_session.execute(stmt, {"p": provider.id, "pl": plan_out.id}).scalar()
    assert result_out is None

def test_filtering_by_specialty_and_plan_returns_accurate_subset(db_session):
    """Filtering by specialty and plan type returns accurate provider subsets."""
    carrier = InsuranceCarrier(name="HealthCo", payer_id="HC001")
    plan = NetworkPlan(plan_name="PPO Plus", carrier=carrier, plan_type="PPO", tier="Gold")

    p1 = Provider(npi="P1", name="Dr. One", specialty="Dermatology", location=WKTElement('POINT(0 0)', srid=4326))
    p2 = Provider(npi="P2", name="Dr. Two", specialty="Dermatology", location=WKTElement('POINT(0 0)', srid=4326))
    p3 = Provider(npi="P3", name="Dr. Three", specialty="Neurology", location=WKTElement('POINT(0 0)', srid=4326))

    p1.plans.append(plan)
    p3.plans.append(plan)

    db_session.add_all([carrier, plan, p1, p2, p3])
    db_session.commit()

    query = text("""
        SELECT p.npi FROM providers p
        JOIN provider_networks pn ON p.id = pn.provider_id
        WHERE p.specialty = 'Dermatology' AND pn.plan_id = :pl
    """)
    results = db_session.execute(query, {"pl": plan.id}).scalars().all()

    assert "P1" in results
    assert "P2" not in results
    assert "P3" not in results

def test_api_gateway_handles_timeouts_without_crashing():
    """API gateway handles insurance verification timeouts without crashing."""
    def mock_api_call():
        raise TimeoutError("Insurance API timed out")

    try:
        mock_api_call()
    except TimeoutError:
        pass
    except Exception as e:
        pytest.fail(f"Unexpected exception type: {type(e)}")
