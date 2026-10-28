#!/usr/bin/env python3
"""One M1 gate: login with packaged UserService backed by a restored Docker named volume.

Only newly created, uniquely named and ownership-labelled test volumes/containers.
Existing osd-m1-user is temporarily stopped, then restored in finally.
"""
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path("/home/andre/projects/openserverdesk/operations")
STAGE = ROOT / "runtime-stage"
PKG = ROOT / "build/openserverdesk-m1-candidate_0.3.0_amd64.deb"
PREFIX = "osd-m1-fixture-"
ORIGINAL = "osd-m1-user"
GATEWAY = "osd-m1-gateway"


def call(*argv, input_text=None, timeout=25):
    response = subprocess.run(argv, input=input_text, capture_output=True,
                              text=True, timeout=timeout)
    if response.returncode:
        raise RuntimeError(f"{argv[0]} operation failed: {response.stderr[-350:]}")
    return response.stdout.strip()


def docker(*args, **kwargs):
    return call("docker", *args, **kwargs)


def api(method, path, data=None):
    argv = ["exec", "-i", GATEWAY, "curl", "-fsS", "--max-time", "5",
            "-X", method, "http://127.0.0.1:18701" + path]
    if data is not None:
        argv += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    return json.loads(docker(*argv, input_text=json.dumps(data) if data is not None else None))


def ready(initialized):
    for _ in range(20):
        try:
            if api("GET", "/v1/users/status")["data"]["initialized"] == initialized:
                return
        except Exception:
            pass
        time.sleep(0.4)
    raise RuntimeError("UserService did not reach expected route state")


def run_copy(command, volumes):
    args = ["run", "--rm", "--network", "none", "--read-only",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "96m", "--pids-limit", "40",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=8m"]
    for name, location, ro in volumes:
        if not name.startswith(PREFIX):
            raise ValueError("non-test volume forbidden")
        args += ["--mount", f"type=volume,src={name},dst={location}" +
                 (",readonly" if ro else "")]
    docker(*args, "--entrypoint", "sh", "busybox:latest", "-ec", command)


def main():
    assert PKG.is_file()
    assert docker("inspect", GATEWAY, "--format", "{{.HostConfig.NetworkMode}}") == "none"
    assert docker("inspect", ORIGINAL, "--format", "{{.State.Running}}") == "true"
    token = secrets.token_hex(8)
    volumes = [PREFIX + token + "-" + part for part in ("source", "backup", "restore")]
    instance = "osd-m1-test-user-" + token
    created = []
    stopped_original = False

    with tempfile.TemporaryDirectory(prefix="m1-named-live-", dir=STAGE) as temp:
        package_dir = Path(temp) / "package"
        package_dir.mkdir()
        call("dpkg-deb", "--extract", str(PKG), str(package_dir))
        candidate = package_dir / "usr/lib/openserverdesk/bin/CasaOS-UserService"
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise RuntimeError("packaged UserService executable missing")
        try:
            for volume in volumes:
                existing = subprocess.run(["docker", "volume", "inspect", volume],
                                          capture_output=True, timeout=10)
                if existing.returncode == 0:
                    raise RuntimeError("refusing to reuse named volume")
                docker("volume", "create", "--label", "osd.m1.fixture=true", volume)
                created.append(volume)

            docker("stop", "-t", "4", ORIGINAL)
            stopped_original = True

            def start_service(volume):
                docker("run", "-d", "--name", instance,
                       "--network", "container:" + GATEWAY,
                       "--read-only", "--cap-drop", "ALL",
                       "--security-opt", "no-new-privileges",
                       "--memory", "240m", "--pids-limit", "100",
                       "--tmpfs", "/tmp:rw,nosuid,nodev,size=20m",
                       "--mount", f"type=bind,src={candidate},dst=/usr/local/bin/userservice,readonly",
                       "--mount", f"type=bind,src={STAGE / 'user-conf'},dst=/etc/casaos,readonly",
                       "--mount", f"type=volume,src={volume},dst=/var/lib/osd-user",
                       "--mount", f"type=bind,src={STAGE / 'run'},dst=/run/osd-stage",
                       "--mount", f"type=bind,src={STAGE / 'log'},dst=/var/log/casaos",
                       "--entrypoint", "/usr/local/bin/userservice", "golang:1.26.8",
                       "-c", "/etc/casaos/user-service.conf", "-db", "/var/lib/osd-user")

            start_service(volumes[0])
            ready(False)
            state = api("GET", "/v1/users/status")
            creds = {"username": "named-" + secrets.token_hex(5),
                     "password": secrets.token_urlsafe(24)}
            created_account = api("POST", "/v1/users/register",
                                  {**creds, "key": state["data"]["key"]})
            if created_account.get("success") != 200:
                raise RuntimeError("synthetic account registration failed")
            if api("POST", "/v1/users/login", creds).get("success") != 200:
                raise RuntimeError("login to source named volume failed")
            print("SOURCE_NAMED_VOLUME_LOGIN_PASS", flush=True)
            docker("stop", "-t", "4", instance)
            docker("rm", instance)

            # No UserService writer running: copy source volume to a backup and
            # then to an independent restored named volume.
            run_copy("cp -a /source/. /backup/",
                     [(volumes[0], "/source", True), (volumes[1], "/backup", False)])
            run_copy("cp -a /backup/. /recovered/",
                     [(volumes[1], "/backup", True), (volumes[2], "/recovered", False)])
            # Prove restored data, not source: start only with restored volume.
            start_service(volumes[2])
            ready(True)
            if api("POST", "/v1/users/login", creds).get("success") != 200:
                raise RuntimeError("login from restored named volume failed")
            print("RESTORED_NAMED_VOLUME_USERSERVICE_LOGIN_PASS", flush=True)
        finally:
            subprocess.run(["docker", "rm", "-f", instance],
                           capture_output=True, timeout=20)
            if stopped_original:
                docker("start", ORIGINAL)
            for volume in reversed(created):
                label = docker("volume", "inspect", "--format",
                              '{{ index .Labels "osd.m1.fixture" }}', volume)
                if label != "true":
                    raise RuntimeError("refusing to remove volume without fixture ownership")
                docker("volume", "rm", volume)
            print("OWNED_FIXTURE_VOLUMES_REMOVED_PASS", flush=True)
        ready(True)
        print("ORIGINAL_STAGING_USER_ROUTE_RESTORED_PASS", flush=True)


if __name__ == "__main__":
    main()
