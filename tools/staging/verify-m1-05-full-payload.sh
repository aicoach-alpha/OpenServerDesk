#!/usr/bin/env bash
# One focused test for the newly completed FULL upstream component payload.
set -euo pipefail
PKG=/home/andre/projects/openserverdesk/operations/build/openserverdesk-m1-candidate_0.5.0_amd64.deb
STAGE=/home/andre/projects/openserverdesk/operations/runtime-stage
WORK=$(mktemp -d "$STAGE/full-payload-XXXXXX")
CONTAINER="osd-m1-ui-$(basename "$WORK" | cut -d- -f3)"
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT
ROOT="$WORK/root"
mkdir -p "$ROOT/var/lib/dpkg/updates" "$ROOT/var/lib/dpkg/info" "$WORK/etc" "$WORK/run" "$WORK/log"
: > "$ROOT/var/lib/dpkg/status"
dpkg --root="$ROOT" --install "$PKG" >/dev/null
test "$(dpkg-query --admindir="$ROOT/var/lib/dpkg" -W -f='${Version}' openserverdesk-m1-candidate)" = "0.5.0"
for binary in CasaOS-Gateway CasaOS-MessageBus CasaOS-UserService CasaOS-AppManagement CasaOS-LocalStorage casaos appfile2compose; do
  test -x "$ROOT/usr/lib/openserverdesk/bin/$binary"
done
test -s "$ROOT/usr/share/openserverdesk/www/index.html"
test -f "$ROOT/usr/share/doc/openserverdesk-m1-candidate/upstream-licenses/CasaOS-UI-NOTICE"
test -f "$ROOT/usr/lib/systemd/system/openserverdesk-m1-candidate.service"
test ! -e "$ROOT/etc/casaos" # No production configuration.
cat > "$WORK/etc/gateway.ini" <<'EOF'
[common]
runtimepath=/run/osd-stage
[gateway]
port=18701
address=127.0.0.1
httpsport=0
EOF
docker run -d --name "$CONTAINER" --network none --read-only \
 --cap-drop ALL --security-opt no-new-privileges --memory 240m --pids-limit 100 \
 --tmpfs /tmp:rw,nosuid,nodev,size=16m \
 --mount "type=bind,src=$ROOT/usr/lib/openserverdesk/bin/CasaOS-Gateway,dst=/usr/local/bin/gateway,readonly" \
 --mount "type=bind,src=$ROOT/usr/share/openserverdesk/www,dst=/var/lib/casaos/www,readonly" \
 --mount "type=bind,src=$WORK/etc,dst=/etc/casaos,readonly" \
 --mount "type=bind,src=$WORK/run,dst=/run/osd-stage" \
 --mount "type=bind,src=$WORK/log,dst=/var/log/casaos" \
 --entrypoint /usr/local/bin/gateway golang:1.26.8 -w /var/lib/casaos/www >/dev/null
READY=0
for _ in $(seq 1 25); do
  if docker exec "$CONTAINER" curl -fsS --max-time 2 http://127.0.0.1:18701/index.html >"$WORK/response.html" 2>/dev/null; then
    READY=1
    break
  fi
  sleep 0.3
done
test "$READY" = 1
grep -Eiq '<html|<!doctype html' "$WORK/response.html"
echo FULL_COMPONENT_INSTALL_AND_DASHBOARD_SERVE_PASS
