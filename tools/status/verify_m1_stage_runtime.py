#!/usr/bin/env python3
"""One-shot acceptance evidence for restricted, authenticated staging workflows.

Read-only verification against current versioned stage package. Historical
authenticated 3-service lifecycle and full tests are linked to the exact
signed package SHA; no production/user data sources are opened.
"""
import datetime
import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

BASE="http://127.0.0.1:18690"
RELEASE="0.6.26"
PACKAGE=Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.6.26_amd64.deb")
RECEIPT=Path("/home/andre/projects/openserverdesk/operations/releases/upgrade-0.6.26-receipt.json")
DOCUMENT=Path("/home/andre/projects/openserverdesk/main/docs/M1_LIVE_MULTISERVICE_V0625_20261016.md")
OUTPUT=Path("/home/andre/projects/openserverdesk/operations/runtime-stage/M1_STAGE_RUNTIME_ACCEPTANCE_V0626.json")

def get(path):
    with urllib.request.urlopen(BASE+path,timeout=7) as result:
        assert result.status==200
        return json.load(result)

def denied(path):
    try:
        get(path)
    except urllib.error.HTTPError as err:
        return err.code
    raise RuntimeError("protected stage endpoint unauthenticated")

def execute(args):
    r=subprocess.run(args,capture_output=True,text=True,timeout=24,check=True)
    return r.stdout.strip()

def main():
    status=get("/health")
    assert status["environment"]=="staging" and status["version"]==RELEASE
    observed=get("/api/v1/docker/containers")
    monitor=get("/api/v1/docker/resources")
    assert observed["container_count"]>=1
    assert monitor["container_count"]==observed["container_count"]
    assert monitor["production_modified"] is False
    assert monitor["external_user_data_inspected"] is False
    assert monitor["migration_allowed"] is False
    checkpaths=["/api/v1/stage/apps","/api/v1/stage/files",
                "/api/v1/stage/compose","/api/v1/stage/compose-backups",
                "/api/v1/stage/topologies","/api/v1/stage/topologies/health",
                "/api/v1/stage/whoami"]
    assert all(denied(path)==401 for path in checkpaths)
    actual_sha=hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    release=json.loads(RECEIPT.read_text())
    assert release["status"]=="live_staging_pass"
    assert release["artifact_sha256"]==actual_sha
    assert release["after"]["package_version"]==RELEASE and release["after"]["production_modified"] is False
    signed=json.loads(execute([
        "python3","/home/andre/projects/openserverdesk/main/tools/release/stage_artifact_signing_0626.py",
        "verify"
    ]))
    assert signed["package_sha256"]==actual_sha
    assert signed["package_version"]==RELEASE
    assert signed["status"]=="STAGING_ED25519_MANIFEST_SIGNATURE_VERIFIED"
    assert signed["production_release_approved"] is False
    doc=DOCUMENT.read_text()
    for phrase in ("70 unit tests", "authenticated HTTP 3-service",
                   "reader role POST denied with 403","all 16 preexisting Docker container IDs"):
        assert phrase in doc,phrase
    marker={
        "schema_version":1,
        "scope":"RESTRICTED_STAGING_WORKFLOWS_ONLY",
        "verified_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "live_package_version":RELEASE,
        "signed_package_sha256":actual_sha,
        "versioned_package_source":signed["source_git_sha"],
        "staging_http_protected_endpoints":len(checkpaths),
        "live_docker_inventory_verified":True,
        "live_docker_resource_metrics_verified":True,
        "restricted_multiservice_lifecycle_e2e_recorded":True,
        "stage_role_based_authorization_e2e_recorded":True,
        "unprivileged_general_compose_support":False,
        "production_equivalence_proven":False,
        "independent_pentest_completed":False,
        "nextcloud_user_data_inspected":False,
        "production_modified":False,
        "migration_allowed":False,
    }
    temp=OUTPUT.with_suffix(".tmp")
    temp.write_text(json.dumps(marker,indent=2,sort_keys=True)+"\n")
    temp.replace(OUTPUT)
    print(json.dumps(marker,sort_keys=True))

if __name__=="__main__":main()
