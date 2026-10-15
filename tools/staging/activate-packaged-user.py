#!/usr/bin/env python3
"""One focused gate: install candidate .deb in staging root, run its real UserService, restore stage."""
import io
import json
import os
import secrets
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

BASE = Path("/opt/openserverdesk-dev")
PACKAGE = BASE / "build/openserverdesk-m1-candidate_0.3.0_amd64.deb"
RUNTIME = BASE / "runtime-stage"
GATEWAY = "osd-m1-gateway"
STAGED_USER = "osd-m1-user"


def command(*args, input_text=None):
    result = subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=35)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1] if len(args)>1 else ''} failed: {result.stderr[:400]}")
    return result.stdout.strip()


def request(method, route, body=None):
    argv = ["docker", "exec", "-i", GATEWAY, "curl", "--max-time", "5", "-sS",
            "-X", method, "-w", "\n%{http_code}", "http://127.0.0.1:18701" + route]
    if body is not None:
        argv += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    raw = command(*argv, input_text=json.dumps(body) if body is not None else None)
    payload, code = raw.rsplit("\n", 1)
    return int(code), json.loads(payload)


def check_control_scripts_absent():
    compressed = subprocess.run(["dpkg-deb", "--ctrl-tarfile", str(PACKAGE)],
                                capture_output=True, timeout=15, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(compressed), mode="r:") as archive:
        entries = {p.name.removeprefix("./") for p in archive.getmembers()}
    if entries - {"", ".", "control", "md5sums"}:
        raise RuntimeError("refusing package with maintainer hooks or unexpected control files")


def main():
    assert PACKAGE.is_file()
    assert command("dpkg-deb", "--field", str(PACKAGE), "Package") == "openserverdesk-m1-candidate"
    assert command("dpkg-deb", "--field", str(PACKAGE), "Version") == "0.3.0"
    check_control_scripts_absent()
    assert command("docker", "inspect", GATEWAY, "--format", "{{.HostConfig.NetworkMode}}") == "none"
    assert command("docker", "inspect", STAGED_USER, "--format", "{{.State.Running}}") == "true"

    with tempfile.TemporaryDirectory(prefix="pkg-activate-", dir=RUNTIME) as scratch:
        root = Path(scratch)
        dpkg_root = root / "install"
        (dpkg_root / "var/lib/dpkg/updates").mkdir(parents=True)
        (dpkg_root / "var/lib/dpkg/info").mkdir()
        (dpkg_root / "var/lib/dpkg/status").write_text("")
        command("dpkg", "--root=" + str(dpkg_root), "--install", str(PACKAGE))
        candidate = dpkg_root / "usr/lib/openserverdesk/bin/CasaOS-UserService"
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RuntimeError("package UserService executable missing")
        db = root / "db"
        db.mkdir()
        instance = f"osd-m1-package-user-{os.getpid()}"
        stopped_original = False
        try:
            command("docker", "stop", "-t", "5", STAGED_USER)
            stopped_original = True
            command(
                "docker", "run", "-d", "--name", instance,
                "--network", "container:" + GATEWAY,
                "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", "240m", "--pids-limit", "100",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=20m",
                "--mount", f"type=bind,src={candidate},dst=/usr/local/bin/userservice,readonly",
                "--mount", f"type=bind,src={RUNTIME / 'user-conf'},dst=/etc/casaos,readonly",
                "--mount", f"type=bind,src={db},dst=/var/lib/osd-user",
                "--mount", f"type=bind,src={RUNTIME / 'log'},dst=/var/log/casaos",
                "--mount", f"type=bind,src={RUNTIME / 'run'},dst=/run/osd-stage",
                "--entrypoint", "/usr/local/bin/userservice",
                "golang:1.26.8", "-c", "/etc/casaos/user-service.conf", "-db", "/var/lib/osd-user")
            for attempt in range(12):
                try:
                    status, body = request("GET", "/v1/users/status")
                    if status == 200 and body["data"]["initialized"] is False:
                        break
                except Exception:
                    pass
                time.sleep(0.5)
            else:
                raise RuntimeError("packaged UserService did not become ready")
            credentials = {"username": "package-" + secrets.token_hex(5),
                           "password": secrets.token_urlsafe(24)}
            status, created = request("POST", "/v1/users/register",
                                      {**credentials, "key": body["data"]["key"]})
            if status != 200 or created.get("success") != 200:
                raise RuntimeError("synthetic registration failed")
            status, auth = request("POST", "/v1/users/login", credentials)
            if status != 200 or auth.get("success") != 200:
                raise RuntimeError("packaged UserService login failed")
            print("PACKAGED_REAL_USERSERVICE_AUTH_PASS", flush=True)
        finally:
            subprocess.run(["docker", "rm", "-f", instance], capture_output=True, timeout=20)
            if stopped_original:
                command("docker", "start", STAGED_USER)
        for attempt in range(12):
            try:
                status, response = request("GET", "/v1/users/status")
                if status == 200 and response["data"]["initialized"] is True:
                    print("ORIGINAL_STAGING_RESTORED_PASS", flush=True)
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("original staging UserService did not recover")


if __name__ == "__main__":
    main()
