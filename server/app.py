"""OpenServerDesk M1.5 staging-only, dependency-free read-only HTTP service."""
import json
import os
from readiness import readiness
from docker_readonly import inventory, InventoryUnavailable
from pathlib import Path
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.3.0-dev"
SUMMARY = Path("/opt/openserverdesk-dev/runtime-stage/M1_PUBLIC_APP_DATA_SUMMARY.json")
ALLOWED_SUMMARY_FIELDS = (
    "checked_at_utc", "container_count", "running_container_count",
    "compose_project_count", "unique_bind_source_count",
    "referenced_named_volume_count", "binds_requiring_operator_review",
    "live_writable_mount_count", "migration_allowed",
    "production_modified", "data_coverage_status",
)
UI = Path(__file__).resolve().parent / "ui"
PROGRESS = Path("/opt/openserverdesk-dev/runtime-stage/progress/latest.json")
PROGRESS_HISTORY = Path("/opt/openserverdesk-dev/runtime-stage/progress/history.jsonl")
PROGRESS_FIELDS = {
    "schema_version", "checked_at_utc", "checked_at_wib", "metric",
    "progress_percent", "milestones", "git_sha", "git_commit_at",
    "git_message", "tracked_working_tree_dirty", "package_version",
    "staging_http", "docker_count", "compose_count",
    "production_service_status", "migration_allowed", "migration_reason",
    "next_priority", "delta_percent_since_previous", "milestone_change_note",
    "new_git_commit_since_previous",
}
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
        if self.path in ("/", "/ui", "/ui/", "/ui/index.html",
                         "/ui/app.js", "/ui/style.css"):
            asset = {"/": "index.html", "/ui": "index.html",
                     "/ui/": "index.html", "/ui/index.html": "index.html",
                     "/ui/app.js": "app.js", "/ui/style.css": "style.css"}[self.path]
            path = UI / asset
            try:
                payload = path.read_bytes()
            except OSError:
                return self.respond(404, {"error": "not_found"})
            self.send_response(200)
            self.send_header("Content-Type", {
                "index.html": "text/html; charset=utf-8",
                "app.js": "text/javascript; charset=utf-8",
                "style.css": "text/css; charset=utf-8"}[asset])
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/v1/m1/progress":
            try:
                if PROGRESS.is_symlink() or PROGRESS.stat().st_size > 32768:
                    raise ValueError("unsafe progress snapshot")
                report = json.loads(PROGRESS.read_text())
                if (set(report) != PROGRESS_FIELDS
                        or report["schema_version"] != 1
                        or report["metric"] != "weighted_scope_accepted_not_time_estimate"
                        or type(report["progress_percent"]) is not int
                        or not 0 <= report["progress_percent"] <= 100
                        or len(report["milestones"]) != 9
                        or report["migration_allowed"] is not False
                        or not all(isinstance(x, dict) and
                                   set(x) == {"id","label","weight_percent",
                                              "verified","evidence_class"}
                                   for x in report["milestones"])):
                    raise ValueError("invalid or untrusted progress snapshot")
                return self.respond(200, report)
            except (OSError, ValueError, TypeError, KeyError):
                return self.respond(503, {"error": "m1_progress_unavailable"})
        if self.path == "/api/v1/m1/progress/history":
            try:
                if PROGRESS_HISTORY.is_symlink() or not PROGRESS_HISTORY.is_file():
                    raise ValueError("missing report history")
                with PROGRESS_HISTORY.open() as stream:
                    lines = deque(stream, maxlen=96)
                if any(len(line) > 4096 for line in lines):
                    raise ValueError("invalid report line")
                return self.respond(200, {
                    "cadence_minutes": 15,
                    "scope": "host_generated_snapshots_not_chat_notifications",
                    "entries": [json.loads(line) for line in lines],
                })
            except (OSError, ValueError, TypeError):
                return self.respond(503, {"error": "m1_progress_history_unavailable"})
        if self.path == "/api/v1/migration/data-coverage":
            try:
                if SUMMARY.is_symlink() or SUMMARY.stat().st_size > 4096:
                    raise ValueError("bad summary file")
                raw = json.loads(SUMMARY.read_text())
                if (set(raw) != set(ALLOWED_SUMMARY_FIELDS)
                        or raw["migration_allowed"] is not False
                        or raw["production_modified"] is not False):
                    raise ValueError("bad summary schema")
                return self.respond(200, {key: raw[key] for key in ALLOWED_SUMMARY_FIELDS})
            except (OSError, ValueError, TypeError):
                return self.respond(503, {"error": "migration_coverage_unavailable"})
        if self.path == "/api/v1/docker/containers":
            try:
                return self.respond(200, inventory())
            except (InventoryUnavailable, ValueError):
                return self.respond(503, {"error": "docker_inventory_unavailable"})
        if self.path == "/health":
            return self.respond(200, {"status":"ok","service":"openserverdesk","version":VERSION,"environment":"staging"})
        if self.path == "/api/v1/migration/readiness":
            return self.respond(200, readiness())
        if self.path == "/api/v1/capabilities":
            return self.respond(200, {"read_only":True,"docker_inventory":True,
                                      "docker_write":False, "migration_activation":False,
                                      "production_changes":False})
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
