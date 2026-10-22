#!/usr/bin/env python3
"""AgentCore HTTP contract using the standard library only.

Later HR work will replace this process with LangGraph + stdio MCP. This
runtime exists to prove VPC packaging, IAM, and InvokeAgentRuntime.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from handler import handle

PORT = int(os.environ.get("PORT", "8080"))


class HelloWorldHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/ping", "/health"):
            self._send(200, {"status": "Healthy"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/invocations":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        self._send(200, handle(payload))

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", PORT), HelloWorldHandler).serve_forever()


if __name__ == "__main__":
    main()
