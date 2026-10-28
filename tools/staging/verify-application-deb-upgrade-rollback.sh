#!/usr/bin/env bash
# One focused gate: real APPLICATION packages 0.3 -> 0.4 -> 0.3, disposable dpkg root only.
set -euo pipefail
PKG=/home/andre/projects/openserverdesk/operations/build
RUNTIME=/home/andre/projects/openserverdesk/operations/runtime-stage
OLD="$PKG/openserverdesk-m1-candidate_0.3.0_amd64.deb"
NEW="$PKG/openserverdesk-m1-candidate_0.4.0_amd64.deb"
test -f "$OLD" && test -f "$NEW"
TEST_ROOT=$(mktemp -d "$RUNTIME/deb-app-rollback-XXXXXX")
trap 'rm -rf "$TEST_ROOT"' EXIT
INSTALL="$TEST_ROOT/root"
mkdir -p "$INSTALL/var/lib/dpkg/updates" "$INSTALL/var/lib/dpkg/info"
: > "$INSTALL/var/lib/dpkg/status"
unit="$INSTALL/usr/lib/systemd/system/openserverdesk-m1-candidate.service"
api="$INSTALL/usr/lib/openserverdesk/server/app.py"
binary="$INSTALL/usr/lib/openserverdesk/bin/CasaOS-UserService"
version() { dpkg-query --admindir="$INSTALL/var/lib/dpkg" -W -f='${Version}' openserverdesk-m1-candidate; }
dpkg --root="$INSTALL" --install "$OLD" >/dev/null 2>&1
test "$(version)" = "0.3.0"
test -x "$binary" && test -f "$api" && test ! -e "$unit"
BASELINE_BIN=$(sha256sum "$binary" | cut -d' ' -f1)
BASELINE_API=$(sha256sum "$api" | cut -d' ' -f1)
dpkg --root="$INSTALL" --install "$NEW" >/dev/null 2>&1
test "$(version)" = "0.4.0"
test -x "$binary" && test -f "$api" && test -f "$unit"
grep -Fq 'ExecStart=/usr/bin/python3 -B /usr/lib/openserverdesk/server/app.py' "$unit"
echo APPLICATION_PACKAGE_UPGRADE_040_PASS
dpkg --root="$INSTALL" --install "$OLD" >/dev/null 2>&1
test "$(version)" = "0.3.0"
test ! -e "$unit"
test "$(sha256sum "$binary" | cut -d' ' -f1)" = "$BASELINE_BIN"
test "$(sha256sum "$api" | cut -d' ' -f1)" = "$BASELINE_API"
echo APPLICATION_PACKAGE_ROLLBACK_030_PASS
