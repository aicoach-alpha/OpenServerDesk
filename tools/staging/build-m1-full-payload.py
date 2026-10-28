#!/usr/bin/env python3
"""Offline, hash-pinned ReCasaOS complete-component payload inside an INERT staging .deb.

Package installs only under OpenServerDesk-specific paths; no hooks/service
starts, no production CasaOS path overwrite, no live Docker interaction.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASSETS = Path("/home/andre/projects/openserverdesk/operations/vendor/m1-release-20261015")
OUT = Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.5.0_amd64.deb")
BASE = Path("/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.4.0_amd64.deb")
SCRATCH = Path("/home/andre/projects/openserverdesk/operations/runtime-stage")
MANIFEST = REPO / "tools/staging/m1-upstream-components.json"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def extract_regular(tar, member_name, output, *, executable=False):
    match = tar.getmember(member_name)
    if not match.isfile():
        raise ValueError("refusing non-regular upstream payload")
    if not member_name.startswith("build/sysroot/") or ".." in Path(member_name).parts:
        raise ValueError("unsafe upstream archive member")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tar.extractfile(match) as origin, output.open("wb") as destination:
        shutil.copyfileobj(origin, destination)
    output.chmod(0o755 if executable else 0o644)


def main():
    locked = json.loads(MANIFEST.read_text())
    with tempfile.TemporaryDirectory(prefix="m1-release-full-", dir=SCRATCH) as temporary:
        root = Path(temporary) / "root"
        root.mkdir()
        subprocess.run(["dpkg-deb", "--extract", str(BASE), str(root)],
                       check=True, stdout=subprocess.DEVNULL)
        binary_dest = root / "usr/lib/openserverdesk/bin"
        docs = root / "usr/share/doc/openserverdesk-m1-candidate"
        ui_root = root / "usr/share/openserverdesk/www"
        template_root = root / "usr/share/openserverdesk/config-templates"
        for binary, checksum in locked["existing_staging_binaries"].items():
            path = binary_dest / binary
            if digest(path) != checksum:
                raise ValueError(f"mismatched pinned staged binary: {binary}")
        for item in locked["assets"]:
            archive = ASSETS / item["filename"]
            if digest(archive) != item["sha256"]:
                raise ValueError(f"upstream archive checksum mismatch: {item['repo']}")
            with tarfile.open(archive, "r:gz") as tar:
                for binary_name, tar_member in item["executables"].items():
                    extract_regular(tar, tar_member, binary_dest / binary_name,
                                    executable=True)
                if item["repo"] == "CasaOS-UI":
                    prefix = "build/sysroot/var/lib/casaos/www/"
                    for member in tar.getmembers():
                        if not member.name.startswith(prefix) or member.isdir():
                            continue
                        relative = Path(member.name[len(prefix):])
                        if not relative.parts or ".." in relative.parts or relative.is_absolute():
                            raise ValueError("unsafe dashboard member")
                        extract_regular(tar, member.name, ui_root / relative)
                    if not (ui_root / "index.html").is_file():
                        raise RuntimeError("upstream dashboard entrypoint not present")
                else:
                    prefix = "build/sysroot/etc/casaos/"
                    for member in tar.getmembers():
                        if member.name.startswith(prefix) and member.name.endswith(".conf.sample"):
                            extract_regular(tar, member.name,
                                            template_root / item["repo"] / Path(member.name).name)
        licenses = docs / "upstream-licenses"
        licenses.mkdir(parents=True)
        for file in (REPO / "tools/staging/upstream-licenses").glob("*"):
            if file.is_file():
                shutil.copy2(file, licenses / file.name)
        shutil.copy2(MANIFEST, docs / "upstream-components.json")
        (docs / "README").write_text(
            "RELEASE CANDIDATE, NOT ACTIVATED. ReCasaOS upstream components "
            "are packaged under isolated OpenServerDesk paths.\n"
            "Do not point components at production CasaOS data or deploy over "
            "running CasaOS. Production cutover rollback/security NOT certified.\n"
        )
        control = root / "DEBIAN"
        control.mkdir()
        (control / "control").write_text(
            "Package: openserverdesk-m1-candidate\nVersion: 0.5.0\n"
            "Section: admin\nPriority: optional\nArchitecture: amd64\n"
            "Maintainer: OpenServerDesk staging <staging@example.invalid>\n"
            "Description: Staging only pinned full-component upstream payload, no activation\n"
        )
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(root),
                        str(OUT)], check=True, stdout=subprocess.DEVNULL)
        print("PINNED_FULL_COMPONENT_PACKAGE_BUILT",OUT)
        print("PACKAGE_SHA256",digest(OUT))


if __name__ == "__main__":
    main()
