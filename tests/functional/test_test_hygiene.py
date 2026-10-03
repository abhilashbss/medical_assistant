"""Hygiene guards that catch broken test modules before the E2E harness does.

These exist because an unresolved git merge conflict in
tests/functional/test_medicine_tracker.py produced a SyntaxError that made
pytest collect zero functional tests, surfacing upstream as a misleading
"No tests found" E2E failure rather than a clear collection error. A
collection-time guard turns that silent zero-collection into an explicit,
localized failure.
"""

import importlib
import pathlib
import py_compile

import pytest

TESTS_DIR = pathlib.Path(__file__).resolve().parent
ROOT_TESTS_DIR = TESTS_DIR.parent
CONFLICT_MARKERS = ("<<<<<<<", "=======", ">>>>>>>")

FUNCTIONAL_MODULES = [
    "tests.functional.test_medicine_tracker",
    "tests.test_medication_tracker",
]


@pytest.mark.parametrize("module_name", FUNCTIONAL_MODULES)
def test_test_module_imports_cleanly(module_name):
    """Each test module must import without syntax/collection errors.

    A merge conflict or syntax error makes pytest skip collection silently,
    which reads upstream as "No tests found" instead of a real failure.
    Importing the module forces the error to surface here, at the module,
    with a useful traceback.
    """
    importlib.import_module(module_name)


def test_no_merge_conflict_markers_in_test_sources():
    """No file under tests/ may contain unresolved git merge conflict markers."""
    offenders = []
    # This file itself documents the markers, so skip it.
    self_path = pathlib.Path(__file__).resolve()
    for src in list(TESTS_DIR.rglob("*.py")) + list(ROOT_TESTS_DIR.glob("*.py")):
        if src.resolve() == self_path:
            continue
        text = src.read_text()
        for marker in CONFLICT_MARKERS:
            if marker in text:
                offenders.append(f"{src.relative_to(ROOT_TESTS_DIR)}: contains {marker!r}")
    assert not offenders, "Unresolved merge conflict markers found:\n" + "\n".join(offenders)


def test_functional_suite_collects_more_than_zero():
    """The functional suite must collect a non-zero number of tests.

    Guards against a regression where the whole functional file fails to
    collect (e.g. import error) and the E2E harness reports zero tests.
    """
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_DIR / "test_medicine_tracker.py"),
         "--collect-only", "-q"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "functional suite failed to collect:\n" + result.stderr
    )
    # --collect-only -q prints one line per test plus a summary line like
    # "35 tests collected". Count the non-blank, non-summary lines.
    collected = [
        line for line in result.stdout.splitlines()
        if line.strip() and "tests collected" not in line and "test" in line.lower()
    ]
    assert len(collected) > 0, (
        "functional suite collected 0 tests — expected the medicine-tracker "
        "functional gate to have cases. Output:\n" + result.stdout
    )