"""OpenServerDesk M1.5 staging-only, dependency-free read-only HTTP service."""
import json
import os
import re
from readiness import readiness
from docker_readonly import inventory, InventoryUnavailable
from docker_metrics import metrics as docker_resource_metrics, MetricsUnavailable
from stage_apps import authenticate as stage_auth, list_apps as stage_list, action as stage_action, AppError, enabled as stage_enabled
from stage_users import authorize as user_authorize, enabled as users_enabled, IdentityError
from pathlib import Path
from collections import deque
from urllib.parse import urlsplit, parse_qs
from stage_storage import (listing as stage_files_list, read as stage_file_read,
                           perform as stage_file_action,
                           create_binary as stage_upload_bytes,
                           download_binary as stage_download_bytes, MAX_FILE as STAGE_MAX_FILE)
from stage_compose import catalog as stage_compose_catalog, list_projects as stage_compose_list, action as stage_compose_action
from stage_topology import list_topologies as topology_list, action as topology_action
from stage_topology_health import inspect as stage_topology_health
from casaos_appstore import catalog as casaos_store_catalog, compatibility as casaos_store_compatibility
from stage_store_installer import list_installs as store_pilot_list, action as store_pilot_action
from stage_store_general import preflight as store_general_preflight, listing as store_general_listing, action as store_general_action
from stage_store_coverage import coverage as stage_store_coverage
from stage_store_compiler import preview as stage_store_compile_preview
from stage_compose_recovery import list_backups as compose_recovery_list, checkpoint as compose_checkpoint, restore as compose_restore, recover as compose_recover, delete as compose_delete
from host_status import status as host_status, HostStatusError
from stage_recovery import list_backups as stage_recovery_list, checkpoint as stage_checkpoint, restore as stage_restore, recover_interrupted as stage_recover_interrupted, delete_checkpoint as stage_delete_checkpoint
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "0.6.5-staging"
# Packaged builds inject this file so /health attests the running RELEASE
# version, rather than a stale source-control developer version.
_PACKAGED_VERSION = Path(__file__).resolve().parent / "release-version.txt"
if _PACKAGED_VERSION.is_file() and not _PACKAGED_VERSION.is_symlink():
    candidate = _PACKAGED_VERSION.read_text().strip()
    if re.fullmatch(r"0\.6\.[0-9]+", candidate):
        VERSION = candidate
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
CUTOVER_PLAN = Path("/opt/openserverdesk-dev/runtime-stage/M1_CUTOVER_PLAN_PUBLIC.json")
COMPOSE_COMPAT = Path("/opt/openserverdesk-dev/runtime-stage/M1_COMPOSE_COMPATIBILITY_PUBLIC.json")
COMPOSE_COMPAT_FIELDS = {
    "schema_version", "scope", "checked_at_utc", "source_config_definitions",
    "valid_definitions", "invalid_definitions", "source_services",
    "mount_declarations", "port_declarations",
    "definitions_needing_additional_compose_support",
    "generally_importable_apps_e2e_verified", "nextcloud_user_files_opened",
    "nextcloud_user_data_copied", "production_modified",
    "general_casaos_compose_parity_proven", "migration_allowed",
}
CUTOVER_FIELDS = {
    "schema_version", "checked_at_utc", "scope", "production_modified",
    "migration_allowed", "user_data_content_accessed", "external_hdd_backup_required",
    "running_containers", "compose_projects", "protected_bind_references_preserved",
    "selected_platform_config_sources", "verified_config_files",
    "verified_sqlite_databases", "gates", "pending_gates", "next_priority",
}
CUTOVER_GATE_KEYS = {
    "platform_scope_not_user_data", "backup_on_independent_ssd",
    "backed_up_platform_source_set_matches_current",
    "verified_ssd_snapshot_and_independent_restore", "six_casaos_units_healthy",
    "cross_service_consistent_snapshot", "production_switch_and_undo_rehearsed",
    "independent_security_and_signed_release", "explicit_maintenance_authorization",
}
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
        if self.path.startswith("/api/v1/stage/download?"):
            try:
                self._stage_auth()
                parsed=urlsplit(self.path)
                values=parse_qs(parsed.query,strict_parsing=True,max_num_fields=2)
                if set(values)!={"name"} or len(values["name"])!=1:
                    raise AppError("invalid_binary_file_query",400)
                filename=values["name"][0]
                data=stage_download_bytes(filename)
                self.send_response(200)
                self.send_header("Content-Type","application/octet-stream")
                self.send_header("Content-Disposition","attachment")
                self.send_header("Cache-Control","no-store")
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("Content-Length",str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            except (TypeError,ValueError):
                return self.respond(400,{"error":"invalid_binary_file_query"})
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/topologies/health":
            try:
                self._stage_auth()
                return self.respond(200,stage_topology_health())
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/topologies":
            try:
                self._stage_auth()
                return self.respond(200,topology_list())
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/whoami":
            try:
                return self.respond(200, self._stage_auth())
            except AppError as err:
                return self.respond(err.status, {"error": err.message})
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
        if self.path == "/api/v1/stage/recovery":
            try:
                self._stage_auth()
                return self.respond(200, stage_recovery_list())
            except AppError as err:
                return self.respond(err.status, {"error":err.message})
        if self.path == "/api/v1/stage/files" or self.path.startswith("/api/v1/stage/files?"):
            try:
                self._stage_auth()
                parsed = urlsplit(self.path)
                values = parse_qs(parsed.query, strict_parsing=True, max_num_fields=2)
                if not values:
                    return self.respond(200, stage_files_list())
                if set(values) != {"name"} or len(values["name"]) != 1:
                    raise AppError("invalid_stage_file_query",400)
                return self.respond(200, stage_file_read(values["name"][0]))
            except (ValueError, TypeError):
                return self.respond(400, {"error":"invalid_stage_file_query"})
            except AppError as err:
                return self.respond(err.status, {"error":err.message})
        if self.path == "/api/v1/stage/store-coverage":
            try:
                self._stage_auth()
                return self.respond(200, stage_store_coverage())
            except (ValueError, OSError):
                return self.respond(503, {"error":"store_coverage_unavailable"})
            except AppError as err:
                return self.respond(err.status, {"error":err.message})
        if self.path == "/api/v1/stage/store-compile" or self.path.startswith("/api/v1/stage/store-compile?"):
            try:
                self._stage_auth()
                params=urlsplit(self.path)
                query=parse_qs(params.query,strict_parsing=True,max_num_fields=1)
                if set(query)!={"id"} or len(query["id"])!=1:
                    raise AppError("invalid_stage_compiler_query",400)
                return self.respond(200,stage_store_compile_preview(query["id"][0]))
            except (TypeError,ValueError):
                return self.respond(400,{"error":"invalid_stage_compiler_query"})
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/store-general" or self.path.startswith("/api/v1/stage/store-general?"):
            try:
                self._stage_auth()
                parsed=urlsplit(self.path)
                if not parsed.query:
                    return self.respond(200,store_general_listing())
                fields=parse_qs(parsed.query,strict_parsing=True,max_num_fields=2)
                if set(fields)!={"id"} or len(fields["id"])!=1:
                    raise AppError("invalid_general_store_query",400)
                return self.respond(200,store_general_preflight(fields["id"][0]))
            except (TypeError,ValueError):
                return self.respond(400,{"error":"invalid_general_store_query"})
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/casaos-store-pilot":
            try:
                self._stage_auth()
                return self.respond(200,store_pilot_list())
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path == "/api/v1/stage/casaos-appstore" or self.path.startswith("/api/v1/stage/casaos-appstore?"):
            try:
                self._stage_auth()
                parsed=urlsplit(self.path)
                if not parsed.query:
                    return self.respond(200,casaos_store_catalog())
                query=parse_qs(parsed.query,strict_parsing=True,max_num_fields=2)
                if set(query)!={"id"} or len(query["id"])!=1:
                    raise AppError("invalid_casaos_store_query",400)
                return self.respond(200,casaos_store_compatibility(query["id"][0]))
            except (ValueError,TypeError):
                return self.respond(400,{"error":"invalid_casaos_store_query"})
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
            except OSError:
                return self.respond(503,{"error":"casaos_store_cache_unavailable"})
        if self.path == "/api/v1/stage/catalog":
            try:
                self._stage_auth()
                return self.respond(200, stage_compose_catalog())
            except AppError as err:
                return self.respond(err.status, {"error": err.message})
        if self.path == "/api/v1/stage/compose-backups":
            try:
                self._stage_auth()
                return self.respond(200, compose_recovery_list())
            except AppError as err:
                return self.respond(err.status, {"error": err.message})
        if self.path == "/api/v1/stage/compose":
            try:
                self._stage_auth()
                return self.respond(200, stage_compose_list())
            except AppError as err:
                return self.respond(err.status, {"error": err.message})
        if self.path == "/api/v1/stage/apps":
            try:
                self._stage_auth()
                return self.respond(200, stage_list())
            except AppError as err:
                return self.respond(err.status, {"error": err.message})
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
                        or len(report["milestones"]) != 11
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
                     "cadence_minutes": None,
                    "automated_monitoring_enabled": False,
                    "scope": "manual_on_demand_server_snapshots",
                    "entries": [json.loads(line) for line in lines],
                })
            except (OSError, ValueError, TypeError):
                return self.respond(503, {"error": "m1_progress_history_unavailable"})
        if self.path == "/api/v1/system/status":
            try:
                return self.respond(200, host_status())
            except HostStatusError:
                return self.respond(503, {"error": "host_status_unavailable"})
        if self.path == "/api/v1/m1/compose-parity":
            try:
                if COMPOSE_COMPAT.is_symlink() or COMPOSE_COMPAT.stat().st_size > 8192:
                    raise ValueError("untrusted Compose parity report")
                report=json.loads(COMPOSE_COMPAT.read_text())
                if (set(report)!=COMPOSE_COMPAT_FIELDS
                        or report["schema_version"]!=1
                        or report["scope"]!="CASAOS_PLATFORM_COMPOSE_YAML_ONLY_NO_USER_DATA"
                        or report["nextcloud_user_files_opened"] is not False
                        or report["nextcloud_user_data_copied"] is not False
                        or report["production_modified"] is not False
                        or report["migration_allowed"] is not False
                        or report["general_casaos_compose_parity_proven"] is not False
                        or any(type(report[key]) is not int or report[key] < 0
                               for key in ("source_config_definitions","valid_definitions",
                                           "invalid_definitions","source_services",
                                           "mount_declarations","port_declarations",
                                           "definitions_needing_additional_compose_support",
                                           "generally_importable_apps_e2e_verified"))
                        or report["valid_definitions"]+report["invalid_definitions"]
                            !=report["source_config_definitions"]
                        or report["generally_importable_apps_e2e_verified"]>
                           report["source_config_definitions"]):
                    raise ValueError("invalid Compose parity data")
                return self.respond(200,report)
            except (OSError,ValueError,KeyError,TypeError):
                return self.respond(503,{"error":"compose_parity_report_unavailable"})
        if self.path == "/api/v1/migration/cutover-plan":
            try:
                if CUTOVER_PLAN.is_symlink() or CUTOVER_PLAN.stat().st_size > 8192:
                    raise ValueError("invalid cutover report file")
                report = json.loads(CUTOVER_PLAN.read_text())
                if (set(report) != CUTOVER_FIELDS
                        or report["schema_version"] != 1
                        or report["scope"] != "CASAOS_PLATFORM_CONFIG_ONLY_NO_USER_DATA_MIGRATION"
                        or report["migration_allowed"] is not False
                        or report["production_modified"] is not False
                        or report["user_data_content_accessed"] is not False
                        or report["external_hdd_backup_required"] is not False
                        or not isinstance(report["gates"], dict)
                        or set(report["gates"]) != CUTOVER_GATE_KEYS
                        or any(type(v) is not bool for v in report["gates"].values())
                        or set(report["pending_gates"]) != {
                            k for k, passed in report["gates"].items() if not passed
                        }
                        or any(type(report[k]) is not int or report[k] < 0
                               for k in ("running_containers", "compose_projects",
                                         "protected_bind_references_preserved",
                                         "selected_platform_config_sources",
                                         "verified_config_files", "verified_sqlite_databases"))):
                    raise ValueError("untrusted release report")
                return self.respond(200, report)
            except (OSError, ValueError, TypeError, KeyError):
                return self.respond(503, {"error": "cutover_plan_unavailable"})
        if self.path == "/api/v1/migration/topology":
            try:
                report_path = Path("/opt/openserverdesk-dev/runtime-stage/M1_PUBLIC_TOPOLOGY_PREFLIGHT.json")
                if report_path.is_symlink() or report_path.stat().st_size > 8192:
                    raise ValueError("unsafe topology report")
                data = json.loads(report_path.read_text())
                fields = {"schema_version","checked_at_utc","scope",
                          "source_inventory_checked_at","production_modified",
                          "migration_allowed","source_count","directory_sources",
                          "file_sources","special_sources","writable_bind_consumers",
                          "shared_writable_source_count","nested_source_pairs",
                          "filesystem_count","required_gates"}
                if (set(data)!=fields or data["schema_version"]!=1
                        or data["migration_allowed"] is not False
                        or data["production_modified"] is not False
                        or data["scope"]!="real_docker_bind_topology_readonly"
                        or not isinstance(data["required_gates"],list)):
                    raise ValueError("unexpected topology report")
                return self.respond(200,data)
            except (OSError,ValueError,TypeError,KeyError):
                return self.respond(503,{"error":"migration_topology_unavailable"})
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
        if self.path == "/api/v1/docker/resources":
            try:
                return self.respond(200, docker_resource_metrics())
            except (MetricsUnavailable, InventoryUnavailable, ValueError):
                return self.respond(503, {"error": "docker_resource_metrics_unavailable"})
        if self.path == "/health":
            return self.respond(200, {"status":"ok","service":"openserverdesk","version":VERSION,"environment":"staging"})
        if self.path == "/api/v1/migration/readiness":
            return self.respond(200, readiness())
        if self.path == "/api/v1/capabilities":
            return self.respond(200, {"read_only":True,"docker_inventory":True,
                                      "docker_write":False,
                                      "isolated_stage_app_lifecycle":stage_enabled(),
                                      "production_app_management":False,
                                      "migration_activation":False,
                                      "production_changes":False})
        return self.respond(404, {"error":"not_found"})
    def _stage_auth(self):
        origin = self.headers.get("Origin")
        allowed = {
            "http://127.0.0.1:" + str(self.server.server_port),
            "http://localhost:" + str(self.server.server_port),
        }
        host = self.headers.get("Host", "")
        if host not in ("127.0.0.1:" + str(self.server.server_port),
                        "localhost:" + str(self.server.server_port)):
            raise AppError("invalid_stage_host_header", 403)
        if origin and origin not in allowed:
            raise AppError("invalid_stage_origin", 403)
        provided = self.headers.get("Authorization")
        if users_enabled():
            try:
                permission = "read" if self.command == "GET" else "write"
                actor = user_authorize(provided, permission)
                return {"actor":actor["actor"], "role":actor["role"],
                        "permissions":actor["permissions"], "authentication":"stage_multiuser"}
            except IdentityError as err:
                raise AppError(err.code,err.status)
        stage_auth(provided)
        return {"actor":"legacy_staging_operator", "role":"administrator",
                "permissions":["read","write"], "authentication":"legacy_stage_only"}

    def do_POST(self):
        if self.path == "/api/v1/stage/upload":
            try:
                self._stage_auth()
                if self.headers.get("Content-Type")!="application/octet-stream":
                    raise AppError("binary_only",415)
                try:
                    size=int(self.headers.get("Content-Length","-1"))
                except ValueError:
                    raise AppError("invalid_binary_length",400)
                if size<0 or size>STAGE_MAX_FILE:
                    raise AppError("binary_upload_size_invalid",413)
                filename=self.headers.get("X-OSD-Filename")
                data=self.rfile.read(size)
                if len(data)!=size:
                    raise AppError("binary_upload_incomplete",400)
                return self.respond(200,stage_upload_bytes(filename,data))
            except AppError as err:
                return self.respond(err.status,{"error":err.message})
        if self.path not in ("/api/v1/stage/apps", "/api/v1/stage/files",
                             "/api/v1/stage/recovery", "/api/v1/stage/compose",
                             "/api/v1/stage/compose-backups", "/api/v1/stage/topologies",
                             "/api/v1/stage/casaos-store-pilot",
                             "/api/v1/stage/store-general"):
            return self.respond(405, {"error":"read_only"})
        try:
            self._stage_auth()
            if self.headers.get("Content-Type", "") != "application/json":
                raise AppError("json_only", 415)
            size = int(self.headers.get("Content-Length", "0"))
            limit = 512 if self.path.endswith(("/apps", "/compose", "/compose-backups", "/topologies")) else 131072
            if size < 2 or size > limit:
                raise AppError("bad_request_size", 400)
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise AppError("invalid_operation_request", 400)
            if self.path.endswith("/store-general"):
                if set(payload)=={"action","id"} and payload.get("action") in ("prepare","install"):
                    return self.respond(200,store_general_action(payload["action"],app_id=payload["id"]))
                if (set(payload)=={"action","project"} and
                        payload.get("action") in ("start","stop","restart","uninstall")):
                    return self.respond(200,store_general_action(payload["action"],project=payload["project"]))
                raise AppError("invalid_general_store_operation",400)
            if self.path.endswith("/casaos-store-pilot"):
                if set(payload)=={"action","id"} and payload.get("action")=="install":
                    return self.respond(200,store_pilot_action("install",app_id=payload["id"]))
                if (set(payload)=={"action","project"} and
                        payload.get("action") in ("start","stop","restart","uninstall")):
                    return self.respond(200,store_pilot_action(payload["action"],project=payload["project"]))
                raise AppError("invalid_store_pilot_operation",400)
            if self.path.endswith("/topologies"):
                if set(payload)=={"action","services"} and payload.get("action")=="install":
                    return self.respond(200,topology_action("install",services=payload["services"]))
                if (set(payload)=={"action","project"} and
                        payload.get("action") in ("start","stop","restart","uninstall")):
                    return self.respond(200,topology_action(payload["action"],project=payload["project"]))
                raise AppError("invalid_topology_request",400)
            if self.path.endswith("/apps"):
                if set(payload) not in ({"action"}, {"action", "name"}):
                    raise AppError("invalid_operation_request", 400)
                return self.respond(200, stage_action(payload["action"], payload.get("name")))
            if self.path.endswith("/compose"):
                if set(payload) not in ({"action", "template"}, {"action", "project"}):
                    raise AppError("invalid_compose_operation_request", 400)
                if not isinstance(payload.get("action"), str):
                    raise AppError("invalid_compose_operation_request", 400)
                return self.respond(200, stage_compose_action(
                    payload["action"], payload.get("project"), payload.get("template")))
            if self.path.endswith("/compose-backups"):
                action = payload.get("action")
                if set(payload) == {"action"} and action == "checkpoint":
                    return self.respond(200, compose_checkpoint())
                if set(payload) == {"action"} and action == "recover":
                    return self.respond(200, compose_recover())
                if set(payload) == {"action", "checkpoint"} and action == "restore":
                    return self.respond(200, compose_restore(payload["checkpoint"]))
                if set(payload) == {"action", "checkpoint"} and action == "delete":
                    return self.respond(200, compose_delete(payload["checkpoint"]))
                raise AppError("invalid_compose_checkpoint_action", 400)
            if self.path.endswith("/recovery"):
                if set(payload) == {"action"} and payload["action"] == "checkpoint":
                    return self.respond(200, stage_checkpoint())
                if set(payload) == {"action"} and payload["action"] == "recover":
                    return self.respond(200, stage_recover_interrupted())
                if set(payload) == {"action","checkpoint"} and payload["action"] == "restore":
                    return self.respond(200, stage_restore(payload["checkpoint"]))
                if set(payload) == {"action","checkpoint"} and payload["action"] == "delete":
                    return self.respond(200, stage_delete_checkpoint(payload["checkpoint"]))
                raise AppError("invalid_stage_recovery_action",400)
            if set(payload) not in ({"action","name"}, {"action","name","content"}):
                raise AppError("invalid_operation_request", 400)
            return self.respond(200, stage_file_action(payload["action"],
                                  payload["name"], payload.get("content")))
        except (TypeError, ValueError, json.JSONDecodeError):
            return self.respond(400, {"error":"invalid_json"})
        except AppError as err:
            return self.respond(err.status, {"error":err.message})
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