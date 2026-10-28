#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/andre/projects/openserverdesk/main
BIN=/home/andre/projects/openserverdesk/operations/bin
OUT=/home/andre/projects/openserverdesk/operations/build
VERSION=0.4.0
STAGE=$(mktemp -d /home/andre/projects/openserverdesk/operations/runtime-stage/m1-package-XXXXXX)
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/DEBIAN" "$STAGE/usr/lib/openserverdesk/bin" "$STAGE/usr/lib/openserverdesk/server" "$STAGE/usr/lib/systemd/system" "$STAGE/usr/share/doc/openserverdesk-m1-candidate"
cat > "$STAGE/DEBIAN/control" <<'EOF'
Package: openserverdesk-m1-candidate
Version: 0.4.0
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
cat > "$STAGE/usr/lib/systemd/system/openserverdesk-m1-candidate.service" <<'EOF'
[Unit]
Description=OpenServerDesk M1 candidate read-only API (opt-in staging)
After=network.target
[Service]
Type=simple
DynamicUser=yes
Environment=OSD_HOST=127.0.0.1
Environment=OSD_PORT=18692
ExecStart=/usr/bin/python3 -B /usr/lib/openserverdesk/server/app.py
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
CapabilityBoundingSet=
SystemCallArchitectures=native
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
echo 'STAGING API UNIT SUPPLIED BUT NOT AUTO-ENABLED. No service hooks; no production migration.' > "$STAGE/usr/share/doc/openserverdesk-m1-candidate/README"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT/openserverdesk-m1-candidate_${VERSION}_amd64.deb" >/dev/null
sha256sum "$OUT/openserverdesk-m1-candidate_${VERSION}_amd64.deb"
