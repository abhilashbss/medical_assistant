"""Isolate: does the shared connection break under concurrent thread use?"""
import sys, threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".vendor")
from medication_tracker.database import Database
from medication_tracker.repository import PrescriptionRepository
from medication_tracker.models import Prescription, PrescriptionStatus

db = Database(":memory:")
db.init_schema()
repo = PrescriptionRepository(db)
rx = repo.create(Prescription(
    patient_id="p1", doctor_id="d1", medicine_name="Amox",
    dosage_amount=500.0, dosage_unit="mg", frequency="daily",
    start_date="2026-01-01T08:00:00+00:00", status=PrescriptionStatus.ACTIVE))

from medication_tracker import PrescriptionDoseLogRepository, DoseLog, DoseEvent
dose_repo = PrescriptionDoseLogRepository(db)

errors = []
def append(i):
    try:
        dose_repo.append(DoseLog(
            prescription_id=rx.id, event=DoseEvent.TAKEN,
            timestamp="2026-01-01T08:00:00+00:00"))
    except Exception as e:
        errors.append((i, repr(e)))

with ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(append, range(40)))

print("errors:", len(errors))
for e in errors[:5]:
    print("  ", e)
print("count:", dose_repo.count(rx.id))