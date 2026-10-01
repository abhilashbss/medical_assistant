#!/usr/bin/env python3
"""Debug script for dose endpoint."""

from medication_tracker import Medication, MedicationRepository, Database, create_app
import tempfile
import os

fd, path = tempfile.mkstemp(suffix='.db')
os.close(fd)

db = Database(path)
db.init_schema()
repo = MedicationRepository(db)

med = Medication(name='Test', dosage='100mg', frequency='daily')
repo.create(med)

print('Medication ID:', med.id)
print('Medication ID type:', type(med.id))
print('Medication ID str:', str(med.id))

app = create_app(db_path=path)
client = app.test_client()

response = client.get(f'/medications/{med.id}')
print('GET response status:', response.status_code)
print('GET response data:', response.get_json())

response = client.post(f'/medications/{med.id}/dose', json={})
print('POST dose response status:', response.status_code)
print('POST dose response data:', response.get_json())

os.remove(path)
