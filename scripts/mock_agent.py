#!/usr/bin/env python3
"""
Minimal mock agent server for testing webhook dispatch.

Listens on port 9998 (or $PORT) and prints every incoming POST payload
to stdout. Register the webhook URL as:

    http://host.docker.internal:9998/webhook   (from Docker)
    http://localhost:9998/webhook               (from host)

Usage:
    python3 scripts/mock_agent.py
    PORT=8888 python3 scripts/mock_agent.py
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        print(json.dumps(body, indent=2))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9998))
    print(f"Mock agent listening on http://0.0.0.0:{port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
