#!/usr/bin/env python3
"""Local E2E guard proxies: Qdrant query-only and Ollama embedding-only."""

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("qdrant", "ollama"), required=True)
parser.add_argument("--port", type=int, required=True)
args = parser.parse_args()
lock = threading.Lock()
stats = {"allowed": 0, "blocked": 0, "qdrantQueries": 0, "embeddingCalls": 0, "generationCalls": 0}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.forward("GET")

    def do_POST(self):
        self.forward("POST")

    def do_PUT(self):
        self.forward("PUT")

    def do_DELETE(self):
        self.forward("DELETE")

    def do_PATCH(self):
        self.forward("PATCH")

    def log_message(self, *_):
        return

    def forward(self, method):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if args.mode == "qdrant":
            allowed = (
                (method == "GET" and self.path == "/collections/zeropay_semantic_claim_pilot_v12")
                or (method == "POST" and self.path == "/collections/zeropay_semantic_claim_pilot_v12/points/query")
            )
        else:
            allowed = method == "POST" and self.path == "/api/embed"
            if allowed:
                try:
                    payload = json.loads(body)
                    allowed = payload.get("model") == "qwen3-embedding:0.6b"
                except (ValueError, TypeError):
                    allowed = False
        if not allowed:
            with lock:
                stats["blocked"] += 1
                if args.mode == "ollama" and self.path in ("/api/chat", "/api/generate"):
                    stats["generationCalls"] += 1
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"request blocked by E2E read-only guard"}')
            print(json.dumps({"event": "blocked", "mode": args.mode, "path": self.path}), flush=True)
            return
        upstream = "http://127.0.0.1:" + ("6333" if args.mode == "qdrant" else "11434") + self.path
        request = Request(upstream, data=body if method != "GET" else None, method=method,
                          headers={"Content-Type": self.headers.get("Content-Type", "application/json")})
        try:
            with urlopen(request, timeout=60) as response:
                data = response.read()
                self.send_response(response.status)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.end_headers()
                self.wfile.write(data)
            with lock:
                stats["allowed"] += 1
                if args.mode == "qdrant" and method == "POST":
                    stats["qdrantQueries"] += 1
                if args.mode == "ollama":
                    stats["embeddingCalls"] += 1
            event = {"event": "allowed", "mode": args.mode, "path": self.path}
            if args.mode == "qdrant" and method == "POST":
                query = json.loads(body)
                payload = json.loads(data)
                conditions = query.get("filter", {}).get("must", [])
                scope = next((item.get("match", {}).get("any", []) for item in conditions
                              if item.get("key") == "restaurantId"), [])
                returned = [point.get("payload", {}).get("restaurantId")
                            for point in payload.get("result", {}).get("points", [])]
                event.update({"candidateRestaurantIds": scope, "returnedRestaurantIds": returned})
            print(json.dumps(event), flush=True)
        except HTTPError as error:
            self.send_response(error.code)
            self.end_headers()
            self.wfile.write(error.read())
        except (URLError, TimeoutError) as error:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(error).encode())


server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
server.daemon_threads = True
threading.Thread(target=server.serve_forever, daemon=True).start()
print(json.dumps({"mode": args.mode, "port": args.port, "guard": "ready"}), flush=True)
try:
    server.serve_forever()
finally:
    server.server_close()
