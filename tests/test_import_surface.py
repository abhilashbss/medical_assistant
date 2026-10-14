"""Test the public API surface to prevent ImportError regressions."""
import pytest

def test_public_api_imports():
    """Ensure that the public API surface of medication_tracker is importable
    without any ImportError. This guards against regressions where internal
    modules are updated but the __init__.py exports are not.
    """
    try:
        import medication_tracker
        from medication_tracker import (
            Prescription,
            PrescriptionStatus,
            ValidationError,
            validate_prescription,
            PrescriptionRepository,
            PrescriptionNotFoundError,
        )
    except ImportError as e:
        pytest.fail(f"Public API import failed: {e}")
