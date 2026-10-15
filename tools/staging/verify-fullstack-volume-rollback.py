#!/usr/bin/env python3
"""One scoped test: packaged Gateway+Bus+UserService restart from restored test volumes.

No host port, production service, existing Docker volume, or original staging
container is touched. This deliberately does not activate a production release.
"""
import fcntl
import json
import signal
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import importlib.util
recovery_file = Path(__file__).with_name("recover-fullstack-orphans.py")
recovery_spec = importlib.util.spec_from_file_location("m1_orphan_recovery", recovery_file)
recovery_module = importlib.util.module_from_spec(recovery_spec)
recovery_spec.loader.exec_module(recovery_module)
recover = recovery_module.recover

STAGE = Path("/opt/openserverdesk-dev/runtime-stage")
PKG = Path("/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.3.0_amd64.deb")
IMAGE = "golang:1.26.8"
BUSYBOX = "busybox:latest"


def command(*args, input_text=None, timeout=28):
    proc = subprocess.run(args, input=input_text, text=True, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"{args[0]} command failed: {proc.stderr[-400:]}")
    return proc.stdout.strip()


def docker(*args, **opts):
    return command("docker", *args, **opts)


def request(gateway, method, route, data=None):
    args = ["exec", "-i", gateway, "curl", "-sS", "--max-time", "5",
            "-w", "\n%{http_code}", "-X", method,
            "http://127.0.0.1:18701" + route]
    if data is not None:
        args += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    raw = docker(*args, input_text=json.dumps(data) if data is not None else None)
    body, status = raw.rsplit("\n", 1)
    return int(status), json.loads(body)


def wait_for(fn, label):
    for _ in range(24):
        try:
            if fn():
                return
        except Exception:
            pass
        time.sleep(.5)
    raise RuntimeError("no verified startup: " + label)


def copy_volume(source, target):
    # Quiesced copy, with read-only source in isolated utility container.
    docker("run", "--rm", "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "96m", "--pids-limit", "40",
           "--tmpfs", "/tmp:rw,nosuid,nodev,size=8m",
           "--mount", f"type=volume,src={source},dst=/source,readonly",
           "--mount", f"type=volume,src={target},dst=/target",
           "--entrypoint", "sh", BUSYBOX, "-ec", "cp -a /source/. /target/")



def require_equal_volumes(source, target):
    """Fail closed if any file contents or tree entries differ after copy."""
    docker("run", "--rm", "--network", "none", "--read-only",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--memory", "96m", "--pids-limit", "40",
           "--mount", f"type=volume,src={source},dst=/source,readonly",
           "--mount", f"type=volume,src={target},dst=/target,readonly",
           "--entrypoint", "sh", BUSYBOX, "-ec",
           "diff -r -q /source /target")


def main():
    if command("dpkg-deb", "-f", str(PKG), "Package") != "openserverdesk-m1-candidate":
        raise RuntimeError("unexpected package")
    token = secrets.token_hex(7)
    prefix = "osd-m1-fixture-" + token
    gw, bus, user = (prefix + "-" + tag for tag in ("gw", "bus", "user"))
    vol = {tag: prefix + "-" + tag for tag in ("us", "bs", "ub", "bb", "ur", "br")}
    created = []
    containers = (user, bus, gw)

    def cleanup_containers():
        for name in containers:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=16)

    with tempfile.TemporaryDirectory(prefix="m1-fullstack-", dir=STAGE) as td:
        temp = Path(td)
        unpack = temp / "package"
        unpack.mkdir()
        command("dpkg-deb", "--extract", str(PKG), str(unpack))
        gateway_binary = unpack / "usr/lib/openserverdesk/bin/CasaOS-Gateway"
        bus_binary = unpack / "usr/lib/openserverdesk/bin/CasaOS-MessageBus"
        user_binary = unpack / "usr/lib/openserverdesk/bin/CasaOS-UserService"
        if not all(path.is_file() and os.access(path, os.X_OK)
                   for path in (gateway_binary, bus_binary, user_binary)):
            raise RuntimeError("incomplete packaged binaries")
        for folder in ("gateway-conf", "bus-conf", "user-conf", "run", "log", "www"):
            (temp / folder).mkdir(mode=0o700)
        (temp / "gateway-conf/gateway.ini").write_text(
            "[common]\nruntimepath=/run/osd-stage\n[gateway]\n"
            "port=18701\naddress=127.0.0.1\nhttpsport=0\n")
        (temp / "bus-conf/message-bus.conf").write_text(
            "[common]\nRuntimePath=/run/osd-stage\n[app]\n"
            "LogPath=/var/log/casaos\nLogSaveName=message-bus\n"
            "LogFileExt=log\nDBPath=/var/lib/osd-bus\n")
        (temp / "user-conf/user-service.conf").write_text(
            "[common]\nRuntimePath=/run/osd-stage\n[app]\n"
            "LogPath=/var/log/casaos\nLogSaveName=user-service\n"
            "LogFileExt=log\nDBPath=/var/lib/osd-user\n"
            "UserDataPath=/var/lib/osd-user\n")

        def start_stack(uvol, bvol):
            docker("run", "-d", "--name", gw, "--label", "osd.m1.fixture=true", "--label", f"osd.m1.owner={token}", "--network", "none",
                   "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--memory", "240m",
                   "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
                   "--mount", f"type=bind,src={gateway_binary},dst=/usr/local/bin/gateway,readonly",
                   "--mount", f"type=bind,src={temp / 'gateway-conf'},dst=/etc/casaos,readonly",
                   "--mount", f"type=bind,src={temp / 'run'},dst=/run/osd-stage",
                   "--mount", f"type=bind,src={temp / 'log'},dst=/var/log/casaos",
                   "--mount", f"type=bind,src={temp / 'www'},dst=/var/lib/casaos/www,readonly",
                   "--entrypoint", "/usr/local/bin/gateway", IMAGE,
                   "-w", "/var/lib/casaos/www")
            wait_for(lambda: bool(docker("exec", gw, "curl", "-fsS",
                                        "http://127.0.0.1:18701/ping")), "gateway ping")
            docker("run", "-d", "--name", bus, "--label", "osd.m1.fixture=true", "--label", f"osd.m1.owner={token}",
                   "--network", "container:" + gw,
                   "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--memory", "240m",
                   "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,nodev,size=20m",
                   "--mount", f"type=bind,src={bus_binary},dst=/usr/local/bin/bus,readonly",
                   "--mount", f"type=bind,src={temp / 'bus-conf'},dst=/etc/casaos,readonly",
                   "--mount", f"type=bind,src={temp / 'run'},dst=/run/osd-stage",
                   "--mount", f"type=bind,src={temp / 'log'},dst=/var/log/casaos",
                   "--mount", f"type=volume,src={bvol},dst=/var/lib/osd-bus",
                   "--entrypoint", "/usr/local/bin/bus", IMAGE,
                   "-c", "/etc/casaos/message-bus.conf")
            wait_for(lambda: (temp / "run/message-bus.url").exists(), "bus URL")
            docker("run", "-d", "--name", user, "--label", "osd.m1.fixture=true", "--label", f"osd.m1.owner={token}",
                   "--network", "container:" + gw,
                   "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges", "--memory", "240m",
                   "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,nodev,size=20m",
                   "--mount", f"type=bind,src={user_binary},dst=/usr/local/bin/userservice,readonly",
                   "--mount", f"type=bind,src={temp / 'user-conf'},dst=/etc/casaos,readonly",
                   "--mount", f"type=bind,src={temp / 'run'},dst=/run/osd-stage",
                   "--mount", f"type=bind,src={temp / 'log'},dst=/var/log/casaos",
                   "--mount", f"type=volume,src={uvol},dst=/var/lib/osd-user",
                   "--entrypoint", "/usr/local/bin/userservice", IMAGE,
                   "-c", "/etc/casaos/user-service.conf", "-db", "/var/lib/osd-user")

        journal = STAGE / ("osd-m1-crash-" + token + ".json")
        state = {"token": token, "containers": [gw, bus, user],
                 "volumes": list(vol.values()), "scratch": str(temp)}
        with journal.open("x") as out:
            json.dump(state, out)
            out.flush()
            os.fsync(out.fileno())
        fd = os.open(STAGE, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        try:
            for v in vol.values():
                if subprocess.run(["docker", "volume", "inspect", v],
                                  capture_output=True, timeout=10).returncode == 0:
                    raise RuntimeError("refusing pre-existing volume")
                docker("volume", "create", "--label", "osd.m1.fixture=true", "--label", f"osd.m1.owner={token}", v)
                created.append(v)
            start_stack(vol["us"], vol["bs"])
            if "--inject-sigkill-after-start" in sys.argv[1:]:
                print("CRASH_INJECTED_TOKEN=" + token, flush=True)
                os.kill(os.getpid(), signal.SIGKILL)
            # Isolated API: register and authenticate one synthetic account.
            wait_for(lambda: request(gw, "GET", "/v1/users/status")[1]["data"]["initialized"] is False,
                     "first UserService")
            code, result = request(gw, "GET", "/v1/users/status")
            assert code == 200 and result["data"]["initialized"] is False
            credential = {"username": "fullstack-" + secrets.token_hex(4),
                          "password": secrets.token_urlsafe(24)}
            code, result = request(gw, "POST", "/v1/users/register",
                                   {**credential, "key": result["data"]["key"]})
            if code != 200 or result.get("success") != 200:
                raise RuntimeError("synthetic registration rejected")
            code, result = request(gw, "POST", "/v1/users/login", credential)
            if code != 200 or result.get("success") != 200:
                raise RuntimeError("initial synthetic login failed")

            # Register local-storage event so UserService can re-subscribe
            # using restored MessageBus state after restart.
            fixture_event = json.dumps([{"sourceID": "local-storage", "name": "rollback-stack",
                                         "propertyTypeList": []}])
            cmd = ("base=$(cat /run/osd-stage/message-bus.url); "
                   "secret=$(cat /run/osd-stage/internal.secret); "
                   "case \"$base\" in http://127.0.0.1:*) ;; *) exit 2;; esac; "
                   f"curl --max-time 4 -fsS -X POST \"$base/v2/message_bus/event_type\" "
                   f"-H \"Authorization: Internal $secret\" "
                   f"-H 'Content-Type: application/json' --data {shlex.quote(fixture_event)}")
            docker("exec", bus, "sh", "-ec", cmd)
            cleanup_containers()
            copy_volume(vol["us"], vol["ub"])
            copy_volume(vol["bs"], vol["bb"])
            require_equal_volumes(vol["us"], vol["ub"])
            require_equal_volumes(vol["bs"], vol["bb"])
            # Damage only the stopped disposable SOURCE database, not backups.
            docker("run", "--rm", "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--mount", f"type=volume,src={vol['us']},dst=/fixture",
                   "--entrypoint", "sh", BUSYBOX, "-ec",
                   "printf 'corrupted fixture' > /fixture/user.db")
            copy_volume(vol["ub"], vol["ur"])
            copy_volume(vol["bb"], vol["br"])
            require_equal_volumes(vol["ub"], vol["ur"])
            require_equal_volumes(vol["bb"], vol["br"])
            start_stack(vol["ur"], vol["br"])
            if "--inject-restored-activation-failure" in sys.argv[1:]:
                raise RuntimeError("INJECTED_RESTORED_ACTIVATION_FAILURE")
            wait_for(lambda: request(gw, "GET", "/v1/users/status")[1]["data"]["initialized"] is True,
                     "restored UserService")
            code, result = request(gw, "POST", "/v1/users/login", credential)
            if code != 200 or result.get("success") != 200:
                raise RuntimeError("restored full-stack login failed")
            # This stack uses its OWN Gateway, MessageBus and restored UserService DB.
            if docker("inspect", gw, "--format", "{{.HostConfig.NetworkMode}}") != "none":
                raise RuntimeError("network isolation lost")
            if docker("inspect", user, "--format", "{{.State.Running}}") != "true":
                raise RuntimeError("restored UserService not running")
            if docker("inspect", bus, "--format", "{{.State.Running}}") != "true":
                raise RuntimeError("restored MessageBus not running")
            wait_for(lambda: "subscribed to" in docker("logs", user),
                     "restored UserService MessageBus subscription")
            print("RESTORED_PACKAGED_THREE_SERVICE_STACK_AUTH_AND_BUS_PASS", flush=True)
        finally:
            cleanup_containers()
            for v in reversed(created):
                label = docker("volume", "inspect", "--format",
                               '{{ index .Labels "osd.m1.fixture" }}', v)
                if label != "true":
                    raise RuntimeError("refusing to remove volume without fixture label")
                docker("volume", "rm", v)
            journal.unlink()
            print("ISOLATED_STACK_AND_VOLUMES_CLEANED_PASS", flush=True)


def run_with_recovery():
    # One running fixture orchestrator per staging area. SIGKILL releases flock.
    lock_path = STAGE / ".osd-m1-fullstack.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another M1 staging orchestrator is running") from exc
        for journal in sorted(STAGE.glob("osd-m1-crash-*.json")):
            match = re.fullmatch(r"osd-m1-crash-([a-f0-9]{14})\.json", journal.name)
            if not match:
                raise RuntimeError("unexpected recovery journal filename")
            recover(match.group(1))
        if "--recover-only" in sys.argv[1:]:
            print("AUTOMATIC_RESTART_RECOVERY_PASS", flush=True)
            return
        main()
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    run_with_recovery()
