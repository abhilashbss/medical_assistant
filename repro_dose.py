"""Reproduce unit #3's dose-log feature E2E against a real uvicorn server."""
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
from api.app import create_app

db_path = "/tmp/repro_unit3_dose_%s.db" % os.getpid()
app = create_app(db_path=db_path)
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

pid = str(uuid4()); doc = str(uuid4())
# create an active prescription
st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Amoxicillin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
assert st == 201, body
rx_id = body["id"]

# 1. append a dose log (taken)
st, body = req("POST", "/prescriptions/%s/dose-logs" % rx_id, {
    "event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"})
print("append taken ->", st, body)
assert st == 201, body

# 2. append a dose log (skipped)
st, body = req("POST", "/prescriptions/%s/dose-logs" % rx_id, {
    "event": "skipped", "timestamp": "2026-01-01T20:00:00+00:00"})
print("append skipped ->", st, body)
assert st == 201, body

# 3. get adherence history (ordered by timestamp ascending)
st, body = req("GET", "/prescriptions/%s/dose-logs" % rx_id)
print("history ->", st, body)
assert st == 200, body
assert len(body) == 2, "expected 2 dose logs, got %d" % len(body)
ts = [log["timestamp"] for log in body]
assert ts == sorted(ts), "dose logs not ordered by timestamp ascending: %s" % ts

# 4. append to nonexistent prescription -> 404
st, body = req("POST", "/prescriptions/no-such-id/dose-logs", {"event": "taken"})
print("append to missing ->", st, body)
assert st == 404, body

# 5. discontinue the prescription, then append -> should be rejected (409)
st, body = req("PATCH", "/prescriptions/%s/discontinue" % rx_id, {"reason": "Adverse reaction"})
assert st == 200, body
st, body = req("POST", "/prescriptions/%s/dose-logs" % rx_id, {"event": "taken"})
print("append to discontinued ->", st, body)
assert st == 409, body

print("DOSE-LOG E2E PASSED")
server.should_exit = True
os.remove(db_path)