"""Drive CONCURRENT requests against a real uvicorn server to expose the
shared-connection thread-safety bug that the sequential TestClient masks."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

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
        with urllib.request.urlopen(r, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, repr(e)

# Create one active prescription
st, body = req("POST", "/prescriptions", {
    "patient_id": "p1", "doctor_id": "d1", "medicine_name": "Amox",
    "dosage_amount": 500.0, "dosage_unit": "mg", "frequency": "daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
assert st == 201, body
rx_id = body["id"]

# Fire many CONCURRENT dose-log appends from separate threads (uvicorn runs
# sync endpoints in a threadpool, so these overlap on the shared connection).
errors = []
def append(i):
    st, body = req("POST", "/prescriptions/%s/dose-logs" % rx_id,
                   {"event": "taken", "timestamp": "2026-01-01T08:00:00+00:00"})
    if st != 201:
        errors.append((i, st, body))

with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(append, range(20)))

print("errors:", errors[:5], "count:", len(errors))
st, body = req("GET", "/prescriptions/%s/dose-logs" % rx_id)
print("history count:", st, len(body) if isinstance(body, list) else body)
server.should_exit = True