#!/usr/bin/env bash
# Install read-only M1 progress cron without affecting unrelated cron jobs.
set -Eeuo pipefail
source_root=/home/andre/projects/openserverdesk/main
report_dir=/home/andre/projects/openserverdesk/operations/runtime-stage/progress
cron_file=/etc/cron.d/openserverdesk-m1-progress
if [[ $EUID != 0 ]]; then echo "Needs operator-approved sudo" >&2; exit 1; fi
[[ -f "$source_root/tools/status/m1_progress_report.py" ]] || exit 2
if [[ ! -d "$report_dir" ]]; then
  install -d -o andre -g andre -m 750 "$report_dir"
fi
[[ ! -L "$report_dir" ]] || exit 2
temp=$(mktemp /tmp/osd-cron-XXXXXX)
trap 'rm -f "$temp"' EXIT
cat > "$temp" <<'CR'
# Only reads local staging API/repository/production service status.
# Every 15 minutes; never sends email, restarts services, or mutates Docker.
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/bin:/bin
MAILTO=""
*/15 * * * * andre /usr/bin/flock -n /home/andre/projects/openserverdesk/operations/runtime-stage/progress/.job.lock /usr/bin/python3 -B /home/andre/projects/openserverdesk/main/tools/status/m1_progress_report.py >>/home/andre/projects/openserverdesk/operations/runtime-stage/progress/cron.log 2>&1
CR
if [[ -e "$cron_file" ]]; then
  cmp -s "$temp" "$cron_file" || {
    echo "Existing monitor configuration changed; refusing overwrite" >&2
    exit 3
  }
else
  install -o root -g root -m 644 "$temp" "$cron_file"
fi
[[ "$(systemctl is-active cron)" == "active" ]] || {
  echo "Cron inactive; monitor not scheduled" >&2
  exit 4
}
runuser -u andre -- /usr/bin/flock -n "$report_dir/.job.lock" /usr/bin/python3 -B "$source_root/tools/status/m1_progress_report.py"
echo M1_15_MIN_MONITOR_CONFIGURED
