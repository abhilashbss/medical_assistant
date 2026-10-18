import pytest
from sqlalchemy import text
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from backend.db.schema import init_db, get_db_session, Provider, InsuranceCarrier, NetworkPlan, provider_networks, search_providers

DB_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    init_db(DB_URL)
    yield

@pytest.fixture
def db_session():
    session = get_db_session()
    yield session
    session.rollback()
    session.close()

def test_search_excludes_out_of_network_providers(db_session):
    """Providers marked as is_in_network=False should be excluded from search."""
    carrier = InsuranceCarrier(name="BlueCross", payer_id="BCBS001")
    plan = NetworkPlan(plan_name="PPO Gold", carrier=carrier)
    
    p_in = Provider(npi="IN1", name="Dr. In", specialty="GP", location=from_shape(Point(0,0), srid=4326))
    p_out = Provider(npi="OUT1", name="Dr. Out", specialty="GP", location=from_shape(Point(0,0), srid=4326))
    
    db_session.add_all([carrier, plan, p_in, p_out])
    db_session.commit()
    
    # p_in is in-network, p_out is explicitly out-of-network
    db_session.execute(provider_networks.insert().values(provider_id=p_in.id, plan_id=plan.id, is_in_network=True))
    db_session.execute(provider_networks.insert().values(provider_id=p_out.id, plan_id=plan.id, is_in_network=False))
    db_session.commit()
    
    results = search_providers(db_session, plan_id=plan.id)
    
    assert len(results) == 1
    assert results[0].npi == "IN1"
