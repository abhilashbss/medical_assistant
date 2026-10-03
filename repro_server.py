"""Start the real WSGI app via a real HTTP server and hit it like an external E2E."""
import json
import threading
import urllib.error
import urllib.request
from uuid import uuid4

from wsgiref.simple_server import make_server
from prescription_tracker.api import create_app

app = create_app(db_path=":memory:")
httpd = make_server("127.0.0.1", 0, app)
port = httpd.server_address[1]

stop = False
def serve():
    while not stop:
        httpd.handle_request()
t = threading.Thread(target=serve, daemon=True)
t.start()

base = "http://127.0.0.1:%d" % port
pid = str(uuid4()); doc = str(uuid4())

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

st, body = req("POST", "/prescriptions", {
    "patient_id": pid, "doctor_id": doc, "medicine_name": "Amoxicillin",
    "dosage_amount": "500", "dosage_unit": "mg", "frequency": "3x daily",
    "start_date": "2026-01-01T08:00:00+00:00"})
print("create ->", st, body)
stop = True