"""Minimal: does sequential real-server E2E with dose logs complete cleanly?"""
import json, sys, threading, time, urllib.request, urllib.error
sys.path.insert(0, ".vendor")
import uvicorn
from api.app import create_app

app = create_app(db_path=":memory:")
config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
threading.Thread(target=server.run, daemon=True).start()
time.sleep(1.0)
sock = list(server.servers)[0].sockets[0]
base = "http://127.0.0.1:%d" % sock.getsockname()[1]

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

st, body = req("POST", "/prescriptions", {
    "patient_id": "p1", "doctor_id": "d1", "medicine_name": "Amox",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
print("create ->", st)
rx = body["id"]
# 5 sequential dose logs
for i in range(5):
    st, body = req("POST", f"/prescriptions/{rx}/dose-logs", {"event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"})
    print(f"append {i} ->", st)
st, body = req("GET", f"/prescriptions/{rx}/dose-logs")
print("history ->", st, len(body) if isinstance(body, list) else body)
server.should_exit = True
print("DONE")