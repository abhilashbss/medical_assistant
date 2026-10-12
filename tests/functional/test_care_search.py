import pytest
from app.models.provider import Provider, ProviderRepository
from app.models.insurance import InsurancePlan, InsuranceRepository

class CareSearchSystem:
    def __init__(self):
        self.provider_repo = ProviderRepository()
        self.insurance_repo = InsuranceRepository()

    def search(self, lat, lon, radius, specialty, plan_id):
        candidates = self.provider_repo.find_nearby(lat, lon, radius, specialty)
        results = []
        for p in candidates:
            if self.insurance_repo.is_in_network(p.id, plan_id):
                results.append(p)
        return results

def test_end_to_end_search():
    system = CareSearchSystem()
    p1 = Provider(id="p1", npi="123", name="Dr. In-Network", specialty="GP", address="SF", latitude=37.77, longitude=-122.41)
    p2 = Provider(id="p2", npi="456", name="Dr. Out-Network", specialty="GP", address="SF", latitude=37.78, longitude=-122.42)
    system.provider_repo.add(p1)
    system.provider_repo.add(p2)

    plan = InsurancePlan(id="plan1", carrier_name="HealthCo", payer_id="HC1", plan_type="PPO", tier="Gold")
    system.insurance_repo.add_plan(plan)
    system.insurance_repo.set_network_status("p1", "plan1", is_in_network=True)
    system.insurance_repo.set_network_status("p2", "plan1", is_in_network=False)

    results = system.search(37.77, -122.41, 10, "GP", "plan1")
    assert len(results) == 1
    assert results[0].id == "p1"
