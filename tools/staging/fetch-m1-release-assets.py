#!/usr/bin/env python3
"""Download only exact SHA256-pinned official archives for M1 full staging payload."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "tools/staging/m1-upstream-components.json"
DESTINATION = Path("/opt/openserverdesk-dev/vendor/m1-release-20261015")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fetch():
    spec = json.loads(MANIFEST.read_text())
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for item in spec["assets"]:
        repo, tag, name, expected = (item[k] for k in ("repo", "tag", "filename", "sha256"))
        if "/" in name or ".." in name or not repo.startswith("CasaOS") or not tag.startswith("v"):
            raise ValueError("invalid pinned asset name")
        path = DESTINATION / name
        if path.exists():
            if digest(path) != expected:
                raise RuntimeError(f"local staged archive does not match SHA256: {name}")
            print("VERIFIED", name, flush=True)
            continue
        url = f"https://github.com/ReCasaOS/{repo}/releases/download/{tag}/{name}"
        fd, tmpname = tempfile.mkstemp(prefix=".osd-download-", dir=DESTINATION)
        try:
            checksum = hashlib.sha256()
            with os.fdopen(fd, "wb") as out, urlopen(
                Request(url, headers={"User-Agent": "OpenServerDesk-staging-pinned-assets"}),
                timeout=45
            ) as incoming:
                for block in iter(lambda: incoming.read(1024 * 1024), b""):
                    out.write(block)
                    checksum.update(block)
                out.flush()
                os.fsync(out.fileno())
            if checksum.hexdigest() != expected:
                raise RuntimeError(f"download SHA256 mismatch: {name}")
            os.replace(tmpname, path)
            print("DOWNLOADED_AND_VERIFIED", name, flush=True)
        finally:
            Path(tmpname).unlink(missing_ok=True)


if __name__ == "__main__":
    fetch()
