"""Unit tests for prescription status transitions and immutability enforcement.

Gate criteria covered:
- Active prescription can transition to completed or discontinued with a timestamped audit row.
- Discontinuation without a reason is rejected at the data layer with a validation error.
- Completed or discontinued prescriptions reject further status transitions (immutability).
- Each status transition records an ISO 8601 timestamp with timezone in the audit table.
- Transitioning to completed does not require a reason; discontinued enforces the reason.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from prescription_tracker.models import Prescription, PrescriptionStatus, StatusTransition
from prescription_tracker.repository import PrescriptionRepository


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _make_active_prescription(patient_id=None, doctor_id=None, medicine_name="Amoxicillin"):
    return Prescription(
        patient_id=patient_id or uuid4(),
        doctor_id=doctor_id or uuid4(),
        medicine_name=medicine_name,
        dosage_amount="500",
        dosage_unit="mg",
        frequency="three times daily",
        start_date="2026-01-01T08:00:00+00:00",
    )


def _assert_tz_aware_iso8601(value: str):
    """Assert a string is a parseable ISO 8601 datetime with timezone info."""
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, f"timestamp '{value}' must include timezone information"


# ----------------------------------------------------------------------
# Active -> completed
# ----------------------------------------------------------------------
class TestCompleteTransition:
    def test_active_can_transition_to_completed(self, repository):
        rx = repository.create(_make_active_prescription())
        assert rx.status == PrescriptionStatus.ACTIVE

        completed = repository.complete(rx.id)
        assert completed.status == PrescriptionStatus.COMPLETED

        refreshed = repository.get_by_id(rx.id)
        assert refreshed.status == PrescriptionStatus.COMPLETED

    def test_complete_inserts_timestamped_audit_row(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.complete(rx.id)

        transitions = repository.get_transitions(rx.id)
        assert len(transitions) == 1
        transition = transitions[0]
        assert transition.from_status == PrescriptionStatus.ACTIVE
        assert transition.to_status == PrescriptionStatus.COMPLETED
        assert transition.transitioned_at is not None
        _assert_tz_aware_iso8601(transition.transitioned_at.isoformat())

    def test_complete_does_not_require_reason(self, repository):
        rx = repository.create(_make_active_prescription())
        completed = repository.complete(rx.id)
        assert completed.status == PrescriptionStatus.COMPLETED

        transitions = repository.get_transitions(rx.id)
        assert transitions[0].reason is None

    def test_transition_timestamp_is_iso8601_with_timezone_in_db(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.complete(rx.id)

        cursor = repository.db.execute(
            "SELECT transitioned_at FROM status_transitions WHERE prescription_id = ?",
            (str(rx.id),),
        )
        row = cursor.fetchone()
        _assert_tz_aware_iso8601(row["transitioned_at"])


# ----------------------------------------------------------------------
# Active -> discontinued (mandatory reason)
# ----------------------------------------------------------------------
class TestDiscontinueTransition:
    def test_active_can_transition_to_discontinued_with_reason(self, repository):
        rx = repository.create(_make_active_prescription())
        discontinued = repository.discontinue(rx.id, reason="Adverse reaction")
        assert discontinued.status == PrescriptionStatus.DISCONTINUED

        refreshed = repository.get_by_id(rx.id)
        assert refreshed.status == PrescriptionStatus.DISCONTINUED

    def test_discontinue_inserts_timestamped_audit_row_with_reason(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.discontinue(rx.id, reason="Adverse reaction")

        transitions = repository.get_transitions(rx.id)
        assert len(transitions) == 1
        transition = transitions[0]
        assert transition.from_status == PrescriptionStatus.ACTIVE
        assert transition.to_status == PrescriptionStatus.DISCONTINUED
        assert transition.reason == "Adverse reaction"
        assert transition.transitioned_at is not None
        _assert_tz_aware_iso8601(transition.transitioned_at.isoformat())

    def test_discontinue_without_reason_raises_validation_error(self, repository):
        rx = repository.create(_make_active_prescription())
        with pytest.raises(ValueError, match="reason"):
            repository.discontinue(rx.id, reason="")

    def test_discontinue_with_none_reason_raises_validation_error(self, repository):
        rx = repository.create(_make_active_prescription())
        with pytest.raises(ValueError, match="reason"):
            repository.discontinue(rx.id, reason=None)

    def test_discontinue_with_whitespace_only_reason_raises(self, repository):
        rx = repository.create(_make_active_prescription())
        with pytest.raises(ValueError, match="reason"):
            repository.discontinue(rx.id, reason="   ")

    def test_discontinue_records_iso8601_timestamp_with_timezone(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.discontinue(rx.id, reason="No longer needed")

        cursor = repository.db.execute(
            "SELECT transitioned_at FROM status_transitions WHERE prescription_id = ?",
            (str(rx.id),),
        )
        row = cursor.fetchone()
        _assert_tz_aware_iso8601(row["transitioned_at"])


# ----------------------------------------------------------------------
# Immutability after lifecycle closure
# ----------------------------------------------------------------------
class TestImmutabilityAfterClosure:
    def test_completed_prescription_rejects_completion_again(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.complete(rx.id)

        with pytest.raises(ValueError, match="cannot transition"):
            repository.complete(rx.id)

    def test_completed_prescription_rejects_discontinuation(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.complete(rx.id)

        with pytest.raises(ValueError, match="cannot transition"):
            repository.discontinue(rx.id, reason="Switching therapies")

    def test_discontinued_prescription_rejects_completion(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.discontinue(rx.id, reason="Adverse reaction")

        with pytest.raises(ValueError, match="cannot transition"):
            repository.complete(rx.id)

    def test_discontinued_prescription_rejects_discontinuation_again(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.discontinue(rx.id, reason="Adverse reaction")

        with pytest.raises(ValueError, match="cannot transition"):
            repository.discontinue(rx.id, reason="Second reason")

    def test_no_second_audit_row_after_terminal_state(self, repository):
        rx = repository.create(_make_active_prescription())
        repository.complete(rx.id)

        with pytest.raises(ValueError):
            repository.discontinue(rx.id, reason="Attempt")

        transitions = repository.get_transitions(rx.id)
        assert len(transitions) == 1, "no second audit row should be inserted after closure"


# ----------------------------------------------------------------------
# Missing prescription handling
# ----------------------------------------------------------------------
class TestTransitionMissingPrescription:
    def test_complete_unknown_prescription_raises(self, repository):
        with pytest.raises(ValueError, match="not found"):
            repository.complete(uuid4())

    def test_discontinue_unknown_prescription_raises(self, repository):
        with pytest.raises(ValueError, match="not found"):
            repository.discontinue(uuid4(), reason="x")


# ----------------------------------------------------------------------
# Model-level transition rule
# ----------------------------------------------------------------------
class TestTransitionRuleModel:
    def test_only_active_can_transition(self):
        assert PrescriptionStatus.transition_allowed(
            PrescriptionStatus.ACTIVE, PrescriptionStatus.COMPLETED
        ) is True
        assert PrescriptionStatus.transition_allowed(
            PrescriptionStatus.ACTIVE, PrescriptionStatus.DISCONTINUED
        ) is True

    def test_terminal_states_cannot_transition(self):
        assert PrescriptionStatus.transition_allowed(
            PrescriptionStatus.COMPLETED, PrescriptionStatus.DISCONTINUED
        ) is False
        assert PrescriptionStatus.transition_allowed(
            PrescriptionStatus.DISCONTINUED, PrescriptionStatus.COMPLETED
        ) is False
        assert PrescriptionStatus.transition_allowed(
            PrescriptionStatus.COMPLETED, PrescriptionStatus.ACTIVE
        ) is False

    def test_status_transition_model_rejects_empty_reason_when_provided(self):
        with pytest.raises(ValueError, match="reason"):
            StatusTransition(
                prescription_id=uuid4(),
                from_status=PrescriptionStatus.ACTIVE,
                to_status=PrescriptionStatus.DISCONTINUED,
                reason="   ",
            )