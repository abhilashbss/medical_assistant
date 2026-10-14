"""Minimal stdlib-only ASGI test client.

Drives a Starlette/FastAPI ASGI app directly without httpx, so tests run on
interpreters whose starlette.testclient requires the unavailable httpx2
package (e.g. Homebrew-managed Python 3.14). Real requests traverse the full
ASGI stack — routing, validation, exception handlers — so status codes and
bodies are production-accurate.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional


class _Response:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        if not self._body:
            return None
        return json.loads(self._body.decode("utf-8"))

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")


class ASGIClient:
    def __init__(self, app):
        self.app = app

    def _build_scope(self, method: str, path: str, query: str = "") -> dict:
        headers = []
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query.encode("utf-8"),
            "headers": headers,
            "client": ("127.0.0.1", 0),
            "server": ("testserver", 80),
            "root_path": "",
            "app": self.app,
            "state": {},
        }
        return scope

    def _request(
        self, method: str, path: str, json_body: Optional[Any] = None
    ) -> _Response:
        body = b""
        headers = []
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers.append((b"content-type", b"application/json"))
            headers.append((b"content-length", str(len(body)).encode("utf-8")))
        elif method in ("POST", "PATCH", "PUT"):
            headers.append((b"content-length", b"0"))

        # Split path and query string.
        query = ""
        raw_path = path
        if "?" in path:
            raw_path, query = path.split("?", 1)

        scope = self._build_scope(method, raw_path, query)
        scope["headers"] = headers

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._send(scope, body))
        finally:
            loop.close()

    async def _send(self, scope: dict, body: bytes) -> _Response:
        sent_body = {"done": False}
        received: dict = {"status": None, "body": bytearray(), "started": False}

        async def receive():
            if not sent_body["done"]:
                sent_body["done"] = True
                return {"type": "http.request", "body": body, "more_body": False}
            # After the request body, block forever — the app sends the
            # response via send() and we break out of the loop below.
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.start":
                received["status"] = message["status"]
                received["started"] = True
            elif message["type"] == "http.response.body":
                received["body"].extend(message.get("body", b""))

        await self.app(scope, receive, send)
        return _Response(received["status"], bytes(received["body"]))

    def get(self, path: str, params: Optional[dict] = None) -> _Response:
        if params:
            from urllib.parse import urlencode

            path = f"{path}?{urlencode(params)}"
        return self._request("GET", path)

    def post(self, path: str, json: Optional[Any] = None) -> _Response:
        return self._request("POST", path, json_body=json)

    def patch(self, path: str, json: Optional[Any] = None) -> _Response:
        return self._request("PATCH", path, json_body=json)