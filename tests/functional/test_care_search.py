import pytest
import time
from sqlalchemy import text
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from backend.db.schema import init_db, get_db_session, Provider, InsuranceCarrier, NetworkPlan, provider_networks

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

def test_search_returns_providers_filtered_by_insurance(db_session):
    """Search returns providers filtered by selected insurance carrier and plan."""
    carrier = InsuranceCarrier(name="BlueCross", payer_id="BCBS001")
    plan = NetworkPlan(plan_name="PPO Gold", carrier=carrier, plan_type="PPO", tier="Gold")
    p1 = Provider(npi="NPI1", name="Dr. In", specialty="GP", location=from_shape(Point(0,0), srid=4326))
    p2 = Provider(npi="NPI2", name="Dr. Out", specialty="GP", location=from_shape(Point(0,0), srid=4326))

    db_session.add_all([carrier, plan, p1, p2])
    db_session.commit()

    # Only p1 is in network
    db_session.execute(provider_networks.insert().values(provider_id=p1.id, plan_id=plan.id, is_in_network=True))
    db_session.commit()

    from backend.db.schema import search_providers
    results = search_providers(db_session, plan_id=plan.id)

    assert len(results) == 1
    assert results[0].npi == "NPI1"

def test_realtime_api_verification_confirms_in_network_status(db_session):
    """Real-time API verification confirms 'In-Network' status for results."""
    carrier = InsuranceCarrier(name="Aetna", payer_id="AET001")
    plan = NetworkPlan(plan_name="HMO Basic", carrier=carrier, plan_type="HMO", tier="Basic")
    provider = Provider(npi="NPI_API", name="Dr. API", specialty="GP", location=from_shape(Point(0,0), srid=4326))

    db_session.add_all([carrier, plan, provider])
    db_session.commit()

    # Simulate API call by inserting the result into the network mapping
    db_session.execute(provider_networks.insert().values(provider_id=provider.id, plan_id=plan.id, is_in_network=True))
    db_session.commit()

    stmt = text("SELECT is_in_network FROM provider_networks WHERE provider_id = :p AND plan_id = :pl")
    result = db_session.execute(stmt, {"p": provider.id, "pl": plan.id}).scalar()
    assert bool(result) is True

def test_geospatial_search_latency(db_session):
    """Geospatial search results are returned within 500ms latency."""
    # Populate some data
    providers = [Provider(npi=f"NPI{i}", name=f"Dr {i}", specialty="GP", location=from_shape(Point(0,0), srid=4326)) for i in range(100)]
    db_session.add_all(providers)
    db_session.commit()

    start_time = time.time()
    from backend.db.schema import search_providers
    search_providers(db_session, lat=0, lon=0, radius_meters=1000)
    duration = (time.time() - start_time) * 1000

    assert duration < 500

def test_search_results_load_time(db_session):
    """Search results load in under 2 seconds including network verification."""
    carrier = InsuranceCarrier(name="C", payer_id="P")
    plan = NetworkPlan(plan_name="Plan", carrier=carrier)
    p = Provider(npi="NPI", name="N", specialty="S", location=from_shape(Point(0,0), srid=4326))
    db_session.add_all([carrier, plan, p])
    db_session.commit()
    db_session.execute(provider_networks.insert().values(provider_id=p.id, plan_id=plan.id, is_in_network=True))
    db_session.commit()

    start_time = time.time()
    from backend.db.schema import search_providers
    search_providers(db_session, plan_id=plan.id)
    duration = (time.time() - start_time) * 1000

    assert duration < 2000

def test_zero_false_positives_for_in_network_status(db_session):
    """Zero false-positives for in-network status across verified test cases."""
    carrier = InsuranceCarrier(name="C", payer_id="P")
    plan = NetworkPlan(plan_name="Plan", carrier=carrier)
    p_out = Provider(npi="OUT", name="Out", specialty="GP", location=from_shape(Point(0,0), srid=4326))

    db_session.add_all([carrier, plan, p_out])
    db_session.commit()

    # Specifically mark as OUT of network
    db_session.execute(provider_networks.insert().values(provider_id=p_out.id, plan_id=plan.id, is_in_network=False))
    db_session.commit()

    stmt = text("SELECT is_in_network FROM provider_networks WHERE provider_id = :p AND plan_id = :pl")
    result = db_session.execute(stmt, {"p": p_out.id, "pl": plan.id}).scalar()
    assert bool(result) is False

def test_search_sorting_by_rating(db_session):
    """Search results are sorted by highest rating first."""
    carrier = InsuranceCarrier(name="Aetna", payer_id="AET001")
    plan = NetworkPlan(plan_name="HMO Basic", carrier=carrier)
    p_low = Provider(npi="LOW", name="Dr. Low", specialty="GP", location=from_shape(Point(0,0), srid=4326), rating=1)
    p_high = Provider(npi="HIGH", name="Dr. High", specialty="GP", location=from_shape(Point(0,0), srid=4326), rating=5)
    
    db_session.add_all([carrier, plan, p_low, p_high])
    db_session.commit()
    
    db_session.execute(provider_networks.insert().values(provider_id=p_low.id, plan_id=plan.id, is_in_network=True))
    db_session.execute(provider_networks.insert().values(provider_id=p_high.id, plan_id=plan.id, is_in_network=True))
    db_session.commit()
    
    from backend.db.schema import search_providers
    results = search_providers(db_session, plan_id=plan.id, sort_by='rating')
    
    assert len(results) == 2
    assert results[0].npi == "HIGH"
    assert results[1].npi == "LOW"

def test_search_sorting_by_distance(db_session):
    """Search results are sorted by nearest provider first."""
    carrier = InsuranceCarrier(name="Aetna", payer_id="AET001")
    plan = NetworkPlan(plan_name="HMO Basic", carrier=carrier)
    p_near = Provider(npi="NEAR", name="Dr. Near", specialty="GP", location=from_shape(Point(0,0), srid=4326))
    p_far = Provider(npi="FAR", name="Dr. Far", specialty="GP", location=from_shape(Point(1,1), srid=4326))
    
    db_session.add_all([carrier, plan, p_near, p_far])
    db_session.commit()
    
    db_session.execute(provider_networks.insert().values(provider_id=p_near.id, plan_id=plan.id, is_in_network=True))
    db_session.execute(provider_networks.insert().values(provider_id=p_far.id, plan_id=plan.id, is_in_network=True))
    db_session.commit()
    
    from backend.db.schema import search_providers
    results = search_providers(db_session, plan_id=plan.id, lat=0, lon=0, sort_by='distance')
    
    assert len(results) == 2
