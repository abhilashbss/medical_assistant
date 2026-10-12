import pytest
from app.models.insurance import InsurancePlan, InsuranceRepository

def test_insurance_network_verification():
    ins_repo = InsuranceRepository()
    plan = InsurancePlan(id="plan1", carrier_name="HealthCo", payer_id="HC1", plan_type="PPO", tier="Gold")
    ins_repo.add_plan(plan)

    provider_id = "prov1"
    ins_repo.set_network_status(provider_id, "plan1", is_in_network=True)

    assert ins_repo.is_in_network(provider_id, "plan1") is True
    assert ins_repo.is_in_network(provider_id, "plan2") is False
