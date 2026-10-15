#!/usr/bin/env python3
"""One fixture-only M1 gate: restore staged config+app data, boot packaged Gateway."""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path("/opt/openserverdesk-dev/runtime-stage")
PKG = Path("/opt/openserverdesk-dev/build/openserverdesk-m1-candidate_0.3.0_amd64.deb")
sys.path.insert(0, "/home/andre/openserverdesk/tools/migration")
from volume_fixture import snapshot, restore


def run(*args):
    p = subprocess.run(args, text=True, capture_output=True, timeout=15)
    if p.returncode:
        raise RuntimeError(f"{args[0]} failure: {p.stderr[:300]}")
    return p.stdout.strip()


def main():
    assert PKG.is_file()
    with tempfile.TemporaryDirectory(prefix="m1-volume-recover-", dir=ROOT) as temp:
        work = Path(temp)
        fixture, backup = work / "fixture", work / "backup"
        (fixture / "config").mkdir(parents=True)
        (fixture / "volume" / "app").mkdir(parents=True)
        (fixture / "runtime").mkdir()
        (fixture / "www").mkdir()
        (fixture / "config" / "gateway.ini").write_text(
            "[common]\nruntimepath=/run/osd-stage\n"
            "[gateway]\nport=18701\naddress=127.0.0.1\nhttpsport=0\n"
        )
        (fixture / "volume" / "app" / "settings.json").write_text('{"theme":"baseline"}')
        (fixture / "volume" / "app" / "state.txt").write_text("original")
        (fixture / "www" / "index.html").write_text("Staging only")
        index = snapshot(fixture, backup)
        # All changes happen while fixture is offline, never on staging/live mounts.
        (fixture / "config" / "gateway.ini").write_text("[gateway]\nport=18888\n")
        (fixture / "volume" / "app" / "settings.json").write_text('{"theme":"changed"}')
        (fixture / "volume" / "app" / "state.txt").unlink()
        (fixture / "volume" / "app" / "unexpected.txt").write_text("new")
        restored = restore(backup, fixture, work)
        if restored != len(index):
            raise RuntimeError("recovery file count mismatch")
        if (fixture / "volume" / "app" / "unexpected.txt").exists():
            raise RuntimeError("rollback did not remove post-snapshot files")
        if json.loads((fixture / "volume" / "app" / "settings.json").read_text()) != {"theme": "baseline"}:
            raise RuntimeError("config/data rollback mismatch")
        if (fixture / "volume" / "app" / "state.txt").read_text() != "original":
            raise RuntimeError("removed volume file not restored")
        print("CONFIG_AND_VOLUME_CONTENT_RESTORED_PASS", flush=True)

        unpack = work / "package"
        unpack.mkdir()
        run("dpkg-deb", "--extract", str(PKG), str(unpack))
        executable = unpack / "usr/lib/openserverdesk/bin/CasaOS-Gateway"
        if not executable.is_file():
            raise RuntimeError("Gateway missing from package")
        # The runtime socket directory is transient, not persistent app data;
        # recreate it after restoring only the snapshotted files.
        (fixture / "runtime").mkdir()
        (fixture / "log").mkdir()
        container = "osd-m1-restored-gw"
        try:
            run("docker", "run", "-d", "--name", container,
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--memory", "240m",
                "--pids-limit", "100", "--tmpfs", "/tmp:rw,nosuid,nodev,size=16m",
                "--mount", f"type=bind,src={executable},dst=/usr/local/bin/gateway,readonly",
                "--mount", f"type=bind,src={fixture / 'config'},dst=/etc/casaos,readonly",
                "--mount", f"type=bind,src={fixture / 'runtime'},dst=/run/osd-stage",
                "--mount", f"type=bind,src={fixture / 'log'},dst=/var/log/casaos",
                "--mount", f"type=bind,src={fixture / 'www'},dst=/var/lib/casaos/www,readonly",
                "--entrypoint", "/usr/local/bin/gateway", "golang:1.26.8",
                "-w", "/var/lib/casaos/www")
            for _ in range(14):
                try:
                    run("docker", "exec", container, "curl", "-fsS", "--max-time", "2",
                        "http://127.0.0.1:18701/ping")
                    print("GATEWAY_BOOT_WITH_RESTORED_CONFIG_PASS", flush=True)
                    break
                except RuntimeError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("Gateway did not boot from restored config")
        finally:
            subprocess.run(["docker", "rm", "-f", container], text=True,
                           capture_output=True, timeout=20)


if __name__ == "__main__":
    main()
