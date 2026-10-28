#!/usr/bin/env python3
"""Focused gate: activate packaged Gateway+MessageBus in disposable isolated staging."""
import os
import subprocess
import tempfile
import time
from pathlib import Path

PACKAGE = Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.3.0_amd64.deb")
BASE = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")


def cmd(*args, timeout=30):
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} command failed: {result.stderr[-500:]}")
    return result.stdout.strip()


def main():
    assert PACKAGE.is_file()
    assert cmd("dpkg-deb", "-f", str(PACKAGE), "Package") == "openserverdesk-m1-candidate"
    with tempfile.TemporaryDirectory(prefix="pkg-gw-bus-", dir=BASE) as scratch:
        root = Path(scratch)
        pkg = root / "install"
        (pkg / "var/lib/dpkg/updates").mkdir(parents=True)
        (pkg / "var/lib/dpkg/info").mkdir()
        (pkg / "var/lib/dpkg/status").write_text("")
        cmd("dpkg", "--root=" + str(pkg), "--install", str(PACKAGE))
        gateway_binary = pkg / "usr/lib/openserverdesk/bin/CasaOS-Gateway"
        bus_binary = pkg / "usr/lib/openserverdesk/bin/CasaOS-MessageBus"
        if not all(f.is_file() and os.access(f, os.X_OK) for f in (gateway_binary, bus_binary)):
            raise RuntimeError("installed candidate binaries missing")
        for folder in ("gw-conf", "bus-conf", "run", "log", "bus-data", "www"):
            (root / folder).mkdir(mode=0o700)
        (root / "gw-conf/gateway.ini").write_text(
            "[common]\nruntimepath=/run/osd-stage\n"
            "[gateway]\nport=18701\naddress=127.0.0.1\nhttpsport=0\n"
        )
        (root / "bus-conf/message-bus.conf").write_text(
            "[common]\nRuntimePath=/run/osd-stage\n"
            "[app]\nLogPath=/var/log/casaos\nLogSaveName=message-bus\n"
            "LogFileExt=log\nDBPath=/var/lib/osd-bus\n"
        )
        gw = "osd-m1-pkg-gw-" + str(os.getpid())
        bus = "osd-m1-pkg-bus-" + str(os.getpid())
        try:
            cmd("docker", "run", "-d", "--name", gw, "--network", "none",
                "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", "240m", "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
                "--mount", f"type=bind,src={gateway_binary},dst=/usr/local/bin/gateway,readonly",
                "--mount", f"type=bind,src={root / 'gw-conf'},dst=/etc/casaos,readonly",
                "--mount", f"type=bind,src={root / 'run'},dst=/run/osd-stage",
                "--mount", f"type=bind,src={root / 'log'},dst=/var/log/casaos",
                "--mount", f"type=bind,src={root / 'www'},dst=/var/lib/casaos/www,readonly",
                "--entrypoint", "/usr/local/bin/gateway", "golang:1.26.8",
                "-w", "/var/lib/casaos/www")
            assert cmd("docker", "inspect", gw, "--format", "{{.HostConfig.NetworkMode}}") == "none"
            for _ in range(20):
                try:
                    cmd("docker", "exec", gw, "curl", "-fsS", "--max-time", "2",
                        "http://127.0.0.1:18701/ping", timeout=5)
                    print("PACKAGED_GATEWAY_PING_PASS", flush=True)
                    break
                except Exception:
                    time.sleep(0.4)
            else:
                raise RuntimeError("packaged Gateway not reachable")
            cmd("docker", "run", "-d", "--name", bus,
                "--network", "container:" + gw, "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", "240m", "--pids-limit", "100",
                "--tmpfs", "/tmp:rw,nosuid,nodev,size=20m",
                "--mount", f"type=bind,src={bus_binary},dst=/usr/local/bin/bus,readonly",
                "--mount", f"type=bind,src={root / 'bus-conf'},dst=/etc/casaos,readonly",
                "--mount", f"type=bind,src={root / 'run'},dst=/run/osd-stage",
                "--mount", f"type=bind,src={root / 'log'},dst=/var/log/casaos",
                "--mount", f"type=bind,src={root / 'bus-data'},dst=/var/lib/osd-bus",
                "--entrypoint", "/usr/local/bin/bus", "golang:1.26.8",
                "-c", "/etc/casaos/message-bus.conf")
            for _ in range(24):
                try:
                    # Authentication stays inside the disposable bus container.
                    cmd("docker", "exec", bus, "sh", "-ec",
                        "base=$(cat /run/osd-stage/message-bus.url); "
                        "secret=$(cat /run/osd-stage/internal.secret); "
                        "case \"$base\" in http://127.0.0.1:*) ;; *) exit 2;; esac; "
                        "curl -fsS --max-time 3 -X POST \"$base/v2/message_bus/event_type\" "
                        "-H \"Authorization: Internal $secret\" "
                        "-H 'Content-Type: application/json' "
                        "--data '[{\"sourceID\":\"package-fixture\",\"name\":\"packaged-gate\","
                        "\"propertyTypeList\":[]}]'", timeout=6)
                    print("PACKAGED_MESSAGEBUS_EVENT_PASS", flush=True)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError("packaged MessageBus did not accept isolated event")
        finally:
            subprocess.run(["docker", "rm", "-f", bus], capture_output=True, timeout=20)
            subprocess.run(["docker", "rm", "-f", gw], capture_output=True, timeout=20)
        if subprocess.run(["docker", "ps", "--filter", f"name=osd-m1-pkg-", "-q"],
                          capture_output=True, text=True, timeout=10).stdout.strip():
            raise RuntimeError("candidate containers remain")
        print("PACKAGED_GATEWAY_BUS_CLEAN_ROLLBACK_PASS", flush=True)


if __name__ == "__main__":
    main()
