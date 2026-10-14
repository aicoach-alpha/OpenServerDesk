#!/usr/bin/env bash
set -euo pipefail
UPSTREAM_ROOT="${UPSTREAM_ROOT:-/opt/openserverdesk-dev/upstream}"
CACHE="${GO_CACHE_ROOT:-/opt/openserverdesk-dev/go-cache}"
IMAGE="${GO_BUILD_IMAGE:-golang:1.26.8}"
for module in CasaOS-Gateway CasaOS-UserService; do
  source_dir="$UPSTREAM_ROOT/$module"
  [[ -f "$source_dir/go.mod" && -d "$CACHE/mod" ]] || { echo "missing source/cache: $module" >&2; exit 1; }
  echo "TESTING $module in isolated Go container"
  docker run --rm --pull=never --network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges \
    --memory=1500m --cpus=2 --pids-limit=200 \
    --mount "type=bind,src=$source_dir,dst=/src,readonly" \
    --mount "type=bind,src=$CACHE/mod,dst=/go/pkg/mod,readonly" \
    --mount "type=bind,src=$CACHE/build,dst=/tmp/go-build" \
    --tmpfs /tmp:rw,exec,nosuid,nodev,size=900m \
    -e GOCACHE=/tmp/go-build -e GOPATH=/go -e GOTOOLCHAIN=local -e GOPROXY=off \
    -w /src "$IMAGE" /bin/bash -ec 'go version; go test ./...'
done
