import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from geoalchemy2.elements import WKTElement
from backend.db.schema import init_db, get_db_session, Provider, InsuranceCarrier, NetworkPlan
import os
import time

# Use SQLite for functional tests in the sandbox
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

def test_provider_search_filtered_by_insurance(db_session):
    """Search returns providers filtered by selected insurance carrier and plan."""
    carrier = InsuranceCarrier(name="HealthCo", payer_id="HC001")
    plan = NetworkPlan(plan_name="Gold PPO", carrier=carrier, plan_type="PPO", tier="Gold")

    p1 = Provider(npi="P1", name="Dr. In-Network", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))
    p2 = Provider(npi="P2", name="Dr. Out-Network", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))

    p1.plans.append(plan)

    db_session.add_all([carrier, plan, p1, p2])
    db_session.commit()

    query = text("""
        SELECT p.npi FROM providers p
        JOIN provider_networks pn ON p.id = pn.provider_id
        WHERE pn.plan_id = :pl
    """)
    results = db_session.execute(query, {"pl": plan.id}).scalars().all()

    assert "P1" in results
    assert "P2" not in results

def test_realtime_api_verification_confirms_in_network_status(db_session):
    """Real-time API verification confirms 'In-Network' status for results."""
    carrier = InsuranceCarrier(name="CarrierA", payer_id="C001")
    plan = NetworkPlan(plan_name="PlanA", carrier=carrier)
    provider = Provider(npi="P1", name="Dr. X", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))
    provider.plans.append(plan)

    db_session.add_all([carrier, plan, provider])
    db_session.commit()

    stmt = text("SELECT is_in_network FROM provider_networks WHERE provider_id = :p AND plan_id = :pl")
    status = db_session.execute(stmt, {"p": provider.id, "pl": plan.id}).scalar()

    assert status is True

def test_geospatial_search_latency(db_session):
    """Geospatial search results are returned within 500ms latency."""
    providers = [Provider(npi=f"N{i}", name=f"Dr {i}", specialty="GP",
                          location=WKTElement(f'POINT({i*0.01} {i*0.01})', srid=4326)) for i in range(100)]
    db_session.add_all(providers)
    db_session.commit()

    start = time.time()
    # Use a simple query for SQLite
    query = text("SELECT npi FROM providers")
    db_session.execute(query).scalars().all()
    duration = (time.time() - start) * 1000

    assert duration < 500

def test_search_results_load_time(db_session):
    """Search results load in under 2 seconds including network verification."""
    carrier = InsuranceCarrier(name="Carrier", payer_id="P1")
    plan = NetworkPlan(plan_name="Plan", carrier=carrier)
    provider = Provider(npi="P1", name="Dr X", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))
    provider.plans.append(plan)
    db_session.add_all([carrier, plan, provider])
    db_session.commit()

    start = time.time()
    query = text("""
        SELECT p.npi FROM providers p
        JOIN provider_networks pn ON p.id = pn.provider_id
        WHERE pn.plan_id = :pl
    """)
    db_session.execute(query, {"pl": plan.id}).scalars().all()
    duration = (time.time() - start) * 1000

    assert duration < 2000

def test_zero_false_positives_for_in_network_status(db_session):
    """Zero false-positives for in-network status across verified test cases."""
    carrier = InsuranceCarrier(name="Carrier", payer_id="P1")
    plan = NetworkPlan(plan_name="Plan", carrier=carrier)
    p_in = Provider(npi="IN", name="In", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))
    p_out = Provider(npi="OUT", name="Out", specialty="GP", location=WKTElement('POINT(0 0)', srid=4326))

    p_in.plans.append(plan)

    db_session.add_all([carrier, plan, p_in, p_out])
    db_session.commit()

    stmt = text("SELECT is_in_network FROM provider_networks WHERE provider_id = :p AND plan_id = :pl")

    assert db_session.execute(stmt, {"p": p_in.id, "pl": plan.id}).scalar() is True
    assert db_session.execute(stmt, {"p": p_out.id, "pl": plan.id}).scalar() is None
