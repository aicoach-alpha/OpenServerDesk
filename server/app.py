"""OpenServerDesk M1.5 staging-only, dependency-free read-only HTTP service."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.1.0-dev"
class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self):
        if self.path == "/health":
            return self.respond(200, {"status":"ok","service":"openserverdesk","version":VERSION,"environment":"staging"})
        if self.path == "/api/v1/capabilities":
            return self.respond(200, {"read_only":True,"migration_activation":False,"production_changes":False})
        return self.respond(404, {"error":"not_found"})
    def do_POST(self):
        self.respond(405, {"error":"read_only"})
    def do_PUT(self):
        self.respond(405, {"error":"read_only"})
    def do_DELETE(self):
        self.respond(405, {"error":"read_only"})
    def log_message(self, *_args):
        pass

def run():
    host=os.environ.get("OSD_HOST","127.0.0.1")
    port=int(os.environ.get("OSD_PORT","18690"))
    if host != "127.0.0.1":
        raise ValueError("staging must bind only to loopback")
    ThreadingHTTPServer((host,port),Handler).serve_forever()

if __name__ == "__main__":
    run()
