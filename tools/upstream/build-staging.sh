#!/usr/bin/env bash
set -euo pipefail
# Builds only to /tmp on an ephemeral Docker container; no host installs or runtime service replacement.
UPSTREAM_ROOT="${UPSTREAM_ROOT:-/opt/openserverdesk-dev/upstream}"
IMAGE="${GO_BUILD_IMAGE:-golang:1.26.8}"
for module in CasaOS-Gateway CasaOS-UserService; do
  source_dir="$UPSTREAM_ROOT/$module"
  [[ -d "$source_dir" && -f "$source_dir/go.mod" ]] || { echo "missing source: $module" >&2; exit 1; }
  docker run --rm --pull=never --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=1400m --cpus=2 --pids-limit=200 \
    --mount "type=bind,src=$source_dir,dst=/src,readonly" \
    --tmpfs /tmp:rw,nosuid,nodev,size=900m \
    -w /src "$IMAGE" /bin/bash -ec 'go version; go test ./...'
done
