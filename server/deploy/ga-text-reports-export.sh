#!/bin/bash
# Authorized operator export. Content is confidential; do not publish or log it.
set -euo pipefail
umask 077
if [ "$EUID" -ne 0 ]; then
  echo 'Run as root on the GA access host.' >&2
  exit 1
fi
export GA_REPORT_EXPORT_LIMIT="${1:-100}"
export GA_REPORT_EXPORT_OFFSET="${2:-0}"
if [[ ! "$GA_REPORT_EXPORT_LIMIT" =~ ^[0-9]+$ || ! "$GA_REPORT_EXPORT_OFFSET" =~ ^[0-9]+$ ]]; then
  echo 'Usage: ga-text-reports-export [limit 1..100] [offset >=0]' >&2
  exit 1
fi
set -a
source /etc/ga-access/environment
set +a
unset PHX_SERVER
export RELEASE_DISTRIBUTION=none
export ERL_FLAGS='+S 2:2 +A 2'
export RELEASE_TMP=/var/lib/ga-access
install -d -o root -g root -m 0700 /var/lib/ga-access-reports
# Encode creation time so reading or changing filesystem access times cannot
# extend the processing copy's expiry. Hourly cleanup starts at age 23 hours.
export_file=$(mktemp "/var/lib/ga-access-reports/reports-$(date +%s)-XXXXXXXX.json")
trap 'unlink "$export_file"' ERR
cd /opt/ga-access/current
bin/ga_server eval 'Logger.configure(level: :warning); {:ok, _} = Application.ensure_all_started(:ga_server); limit = System.fetch_env!("GA_REPORT_EXPORT_LIMIT") |> String.to_integer(); offset = System.fetch_env!("GA_REPORT_EXPORT_OFFSET") |> String.to_integer(); GA.Access.TextReports.list_for_operator(limit, offset) |> Jason.encode!() |> IO.puts()' > "$export_file"
printf '%s\n' "$export_file"
