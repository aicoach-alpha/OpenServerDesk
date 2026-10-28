#!/usr/bin/env bash
set -euo pipefail
BIN_DIR="${BIN_DIR:-/home/andre/projects/openserverdesk/operations/bin}"
for component in CasaOS-Gateway CasaOS-UserService; do
  binary="$BIN_DIR/$component"
  test -s "$binary"
  file "$binary" | grep -q 'ELF 64-bit.*x86-64'
  output=$(timeout 8 docker run --rm --pull=never --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=48 --memory=128m --mount "type=bind,src=$binary,dst=/test-binary,readonly" --entrypoint /test-binary golang:1.26.8 --help 2>&1 || true)
  case "$output" in *"Usage of"* ) echo "$component ISOLATED_CLI_PASS";; *) echo "$component ISOLATED_CLI_FAIL" >&2; exit 1;; esac
  sha256sum "$binary"
done
