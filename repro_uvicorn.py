"""Drive the full feature E2E against the module-level app (uvicorn api.app:app),
which uses create_app() with db_path=None -> :memory: and a single shared connection."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from uuid import uuid4

sys.path.insert(0, ".vendor")
import uvicorn

# This is what `uvicorn api.app:app` does: imports the module-level `app`.
import api.app as appmod
app = appmod.app  # create_app() with :memory:

config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
t = threading.Thread(target=server.run, daemon=True)
t.start()
time.sleep(1.0)
sock = list(server.servers)[0].sockets[0]
base = "http://127.0.0.1:%d" % sock.getsockname()[1]
print("server at", base)

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, str(e)

pid = "patient-1"; doc = "doctor-1"
# Full lifecycle from the E2E description:
st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Amoxicillin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
print("create ->", st, body if st != 201 else body.get("id"))
assert st == 201, body
rx_id = body["id"]

# history sorted by start date
st, body = req("GET", "/patients/%s/prescriptions" % pid)
print("history ->", st, len(body) if isinstance(body, list) else body)
assert st == 200

# discontinue with mandatory reason
st, body = req("PATCH", "/prescriptions/%s/discontinue" % rx_id, {"reason": "Adverse reaction"})
print("discontinue ->", st, body.get("status") if isinstance(body, dict) else body)
assert st == 200 and body["status"] == "discontinued"

# validation: missing field
st, body = req("POST", "/prescriptions", {"patient_id": pid, "doctor_id": doc,
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily", "start_date": "2026-01-01T08:00:00+00:00"})
print("missing field ->", st)
assert st in (400, 422)

# validation: end<start
st, body = req("POST", "/prescriptions", {"patient_id": pid, "doctor_id": doc,
    "medicine_name": "Naproxen", "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-02-01T08:00:00+00:00", "end_date": "2026-01-01T08:00:00+00:00"})
print("end<start ->", st)
assert st == 400

# duplicate active
st, body = req("POST", "/prescriptions", {"patient_id": pid, "doctor_id": doc,
    "medicine_name": "Metformin", "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-03-01T08:00:00+00:00"})
print("create metformin ->", st)
st2, body2 = req("POST", "/prescriptions", {"patient_id": pid, "doctor_id": doc,
    "medicine_name": "Metformin", "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-04-01T08:00:00+00:00"})
print("dup active ->", st2)
assert st2 == 409

# Now unit #3's feature: dose logs
st, body = req("POST", "/prescriptions", {"patient_id": pid, "doctor_id": doc,
    "medicine_name": "Ibuprofen", "dosage_amount": 200.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-05-01T08:00:00+00:00"})
print("create ibuprofen ->", st)
rx2 = body["id"]
st, body = req("POST", "/prescriptions/%s/dose-logs" % rx2, {"event": "taken", "timestamp": "2026-05-01T08:00:00+00:00"})
print("dose-log append ->", st, body)
assert st == 201, body
st, body = req("GET", "/prescriptions/%s/dose-logs" % rx2)
print("dose-log history ->", st, body)
assert st == 200 and len(body) == 1

print("FULL E2E PASSED")
server.should_exit = True