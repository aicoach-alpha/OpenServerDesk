#!/usr/bin/env python3
"""Focused M1: real disposable Docker named-volume snapshot and restore only.

All containers run network=none. Only freshly created osd-m1-fixture-*
volumes are accessed or removed. Existing volumes are never mounted.
"""
import secrets
import subprocess

PREFIX = "osd-m1-fixture-"
IMAGE = "busybox:latest"


def docker(*args):
    result = subprocess.run(
        ["docker", *args], text=True, capture_output=True, timeout=25
    )
    if result.returncode:
        raise RuntimeError(f"docker operation failed: {result.stderr[-500:]}")
    return result.stdout.strip()


def container(script, *mounts):
    args = [
        "run", "--rm", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "96m", "--pids-limit", "40",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=8m",
    ]
    for name, path, readonly in mounts:
        if not name.startswith(PREFIX):
            raise ValueError("nonfixture volume forbidden")
        args += [
            "--mount",
            f"type=volume,src={name},dst={path}" + (",readonly" if readonly else ""),
        ]
    return docker(*args, "--entrypoint", "sh", IMAGE, "-ec", script)


def main():
    suffix = secrets.token_hex(8)
    source = PREFIX + suffix + "-source"
    backup = PREFIX + suffix + "-backup"
    restored = PREFIX + suffix + "-restored"
    created = []
    try:
        for name in (source, backup, restored):
            existing = subprocess.run(
                ["docker", "volume", "inspect", name],
                text=True, capture_output=True, timeout=10
            )
            if existing.returncode == 0:
                raise RuntimeError("refusing to reuse existing Docker volume")
            docker("volume", "create", "--label", "osd.m1.fixture=true", name)
            if docker("volume", "inspect", "--format",
                      '{{ index .Labels "osd.m1.fixture" }}', name) != "true":
                raise RuntimeError("fixture ownership label missing")
            created.append(name)

        container(
            'mkdir -p /source/app/config; '
            'printf "baseline-settings" > /source/app/config/settings.ini; '
            'printf "original-state" > /source/app/state.txt; '
            'chmod 640 /source/app/config/settings.ini',
            (source, "/source", False),
        )
        # No writer remains alive during backup.
        container("cp -a /source/. /backup/",
                  (source, "/source", True), (backup, "/backup", False))
        container(
            'printf "changed" > /source/app/config/settings.ini; '
            'rm /source/app/state.txt; '
            'printf "new-file" > /source/app/unexpected.txt',
            (source, "/source", False),
        )
        # Restore to a *fresh* volume: never destroy or overwrite production data.
        container("cp -a /backup/. /restored/",
                  (backup, "/backup", True), (restored, "/restored", False))
        result = container(
            'test "$(cat /restored/app/config/settings.ini)" = "baseline-settings"; '
            'test "$(cat /restored/app/state.txt)" = "original-state"; '
            'test ! -e /restored/app/unexpected.txt; '
            'test "$(stat -c %a /restored/app/config/settings.ini)" = "640"; '
            'cmp /backup/app/config/settings.ini /restored/app/config/settings.ini; '
            'cmp /backup/app/state.txt /restored/app/state.txt; '
            'test "$(cat /source/app/config/settings.ini)" = "changed"; '
            'printf "DOCKER_NAMED_VOLUME_RESTORE_PASS"',
            (backup, "/backup", True), (restored, "/restored", True),
            (source, "/source", True),
        )
        if "DOCKER_NAMED_VOLUME_RESTORE_PASS" not in result:
            raise RuntimeError("missing fixture restore proof")
        print(result)
    finally:
        # Each name was generated in this invocation and created above.
        for name in reversed(created):
            if docker("volume", "inspect", "--format",
                      '{{ index .Labels "osd.m1.fixture" }}', name) != "true":
                raise RuntimeError("refusing to remove unowned volume")
            docker("volume", "rm", name)
        print("FIXTURE_VOLUMES_REMOVED_PASS")


if __name__ == "__main__":
    main()
