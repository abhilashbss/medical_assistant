"""Pytest hooks for functional test evidence capture.

Ensures the .see/e2e-artifacts/ directory exists so the evidence test can
write its console transcript there when the gate command runs.
"""
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / ".see" / "e2e-artifacts"


def pytest_sessionstart(session):
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)