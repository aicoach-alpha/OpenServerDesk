#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/andre/openserverdesk
BIN=/opt/openserverdesk-dev/bin
OUT=/opt/openserverdesk-dev/build
STAGE=$(mktemp -d /opt/openserverdesk-dev/runtime-stage/m1-package-XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/lib/openserverdesk/bin" "$STAGE/usr/lib/openserverdesk/server" "$STAGE/usr/share/doc/openserverdesk-m1-candidate"
cat > "$STAGE/DEBIAN/control" <<'EOF'
Package: openserverdesk-m1-candidate
Version: 0.3.0
Section: admin
Priority: optional
Architecture: amd64
Maintainer: OpenServerDesk staging <staging@example.invalid>
Description: Isolated M1 candidate payload; no production activation
EOF
for item in CasaOS-Gateway CasaOS-MessageBus CasaOS-UserService; do
    install -m 0755 "$BIN/$item" "$STAGE/usr/lib/openserverdesk/bin/$item"
done
install -m 0644 "$ROOT/server/app.py" "$STAGE/usr/lib/openserverdesk/server/app.py"
install -m 0644 "$ROOT/server/readiness.py" "$STAGE/usr/lib/openserverdesk/server/readiness.py"
echo 'NON-ACTIVATING STAGING PAYLOAD: no service setup, no production migration.' > "$STAGE/usr/share/doc/openserverdesk-m1-candidate/README"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT/openserverdesk-m1-candidate_0.3.0_amd64.deb" >/dev/null
sha256sum "$OUT/openserverdesk-m1-candidate_0.3.0_amd64.deb"
