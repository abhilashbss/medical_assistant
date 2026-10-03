"""Reproduce the feature E2E against a real uvicorn HTTP server."""
import json
import sys
import threading
import urllib.error
import urllib.request
import os
from uuid import uuid4

sys.path.insert(0, ".vendor")

# Use an on-disk DB so the server (and any subprocess) shares state.
db_path = "/tmp/repro_unit3_%s.db" % os.getpid()
os.environ["MEDICATION_TRACKER_DB"] = db_path
# The app's create_app(db_path) signature takes db_path directly; the module-level
# `app = create_app()` uses in-memory. We drive a fresh server with an explicit path.

import uvicorn
from api.app import create_app

app = create_app(db_path=db_path)
config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
port_holder = {}

def run():
    # patch to get the bound port
    orig = server.run
    import socket
    # We'll just run; read port after start via a socket hook is complex.
    server.run()
t = threading.Thread(target=server.run, daemon=True)
t.start()

# Wait for server up and discover port
import time
time.sleep(1.0)
# uvicorn Server.config.servers is set after run; read port from there
sock = list(server.servers)[0].sockets[0] if getattr(server, "servers", None) else None
base = "http://127.0.0.1:%d" % (sock.getsockname()[1] if sock else 8000)
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
# 1. create
st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Amoxicillin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
print("create ->", st, body if st != 201 else body.get("id"))
assert st == 201, body
rx_id = body["id"]

# 2. retrieve
st, body = req("GET", "/prescriptions/%s" % rx_id)
print("retrieve ->", st)
assert st == 200

# 3. history sorted
st, body = req("GET", "/patients/%s/prescriptions" % pid)
print("history ->", st, "count=%d" % len(body))
assert st == 200 and len(body) == 1

# 4. discontinue with reason
st, body = req("PATCH", "/prescriptions/%s/discontinue" % rx_id, {"reason": "Adverse reaction"})
print("discontinue ->", st, body.get("status") if isinstance(body, dict) else body)
assert st == 200 and body["status"] == "discontinued"

# 5. missing field -> 400/422
bad = {"patient_id": pid, "doctor_id": doc, "dosage_amount": 500.0, "dosage_unit": "mg",
       "frequency": "3x daily", "start_date": "2026-01-01T08:00:00+00:00"}
st, body = req("POST", "/prescriptions", bad)
print("missing medicine ->", st)
assert st in (400, 422)

# 6. end<start -> 400
st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Naproxen",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-02-01T08:00:00+00:00", "end_date": "2026-01-01T08:00:00+00:00"})
print("end<start ->", st)
assert st == 400, body

# 7. dup active -> 409
st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Metformin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-03-01T08:00:00+00:00"})
print("create metformin ->", st)
st2, body2 = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Metformin",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-04-01T08:00:00+00:00"})
print("dup active ->", st2, body2)
assert st2 == 409

print("E2E PASSED")
server.should_exit = True
os.remove(db_path)