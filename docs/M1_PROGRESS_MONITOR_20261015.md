> UPDATED 16 October 2026: The user requested the automated M1 jobs OFF.
> Both the ChatGPT automation and NAS 15-minute cron job are disabled.
> This file records their historical implementation but they are NOT
> currently running. Status checks are one-shot/on-demand only.
> Real platform-only SSD backup/restore was verified and weighted gate
> scope updated: 8 points accepted, 12 points reserved for cross-service
> atomic consistency. The current verified score is 40/100 and MUST NOT
> be reported as time remaining.

# OPERATOR UPDATE (2026-10-15 17:58 WIB): BOTH M1 AUTONOMOUS TASKS STOPPED

At the user's explicit request the ChatGPT hourly M1 task is disabled and the
server cron entry /etc/cron.d/openserverdesk-m1-progress was removed.
Historical snapshots remain for audit; nothing is scheduled to collect new
reports automatically. Browser M1 progress is now explicitly marked historical.

---

# M1 auditable 15-minute progress monitoring

Running on andre-nas staging only. ChatGPT itself cannot send scheduled
messages every 15 minutes.

- Generator: tools/status/m1_progress_report.py. Read-only fixed API and
  subprocess calls. User andre; cron on every quarter hour (*/15 * * * *).
- Cron: /etc/cron.d/openserverdesk-m1-progress, installed idempotently by
  tools/status/install-15min-monitor.sh. Unrelated cron jobs untouched.
- Dashboard: http://127.0.0.1:18690/ui, loopback-only on NAS.
  The page refreshes each minute; server collects a new snapshot each 15.
- Endpoints: GET /api/v1/m1/progress and /api/v1/m1/progress/history.
  Report paths: /opt/openserverdesk-dev/runtime-stage/progress/latest.json
  and history.jsonl; latest 96 snapshots are viewable from the API.
- Report includes timestamp WIB, commit hash/time, package version,
  health and Docker API results, real container/Compose counts,
  production service status, weighted acceptance, and interval delta.
- Weights: six-component package 8%, six-service staged boot 4%, real
  readonly Docker UI 8%, live data inventory 4%, isolated two-project
  data recovery 8%, full authenticated management integration 18%, all
  real app data backup/restore 20%, activation/rollback 20%, and signed
  production release/security review 10%. Total 100%. Baseline 32%.
- Score means **accepted milestone scope, never remaining time**.
  No automatic increase from elapsed time, code commits or test volume.
  Historical tests are labelled separately from live runtime checks.
  A +0% snapshot explicitly reports that no new milestone was verified.
- The UI warns STALE when server snapshot age exceeds 21 minutes. Historical
  JSONL is not a third-party cryptographic attestation; OS operators can
  edit it. It is evidence of on-host checks, not proof of independent audit.
- ChatGPT scheduled notifications are limited to one per hour. These
  15-minute reports are host-side snapshots, NOT proactive ChatGPT messages.
- Staging is bound to 127.0.0.1; never expose it publicly without
  authentication. Nothing modifies CasaOS production or application data.
