#!/usr/bin/env bash
set -euo pipefail
# M1-only fixture: the bus and gateway MUST be staging and network-isolated.
container="${OSD_BUS_CONTAINER:-osd-m1-bus}"
[[ "$container" == "osd-m1-bus" ]] || { echo "Non-staging container rejected" >&2; exit 1; }
network=$(docker inspect "$container" --format '{{.HostConfig.NetworkMode}}')
[[ "$network" == "container:osd-m1-gateway" || "$network" == container:* ]] || { echo "Unexpected network mode" >&2; exit 1; }
docker exec "$container" sh -ec '
  base=$(cat /run/osd-stage/message-bus.url)
  secret=$(cat /run/osd-stage/internal.secret)
  case "$base" in http://127.0.0.1:* ) ;; *) echo "Non-loopback endpoint rejected" >&2; exit 1;; esac
  curl -fsS -X POST "$base/v2/message_bus/event_type" -H "Authorization: Internal $secret" -H "Content-Type: application/json" --data "[{\"sourceID\":\"local-storage\",\"name\":\"osd-staging-check\",\"propertyTypeList\":[]}]"
'
echo "SYNTHETIC_EVENT_REGISTERED"
