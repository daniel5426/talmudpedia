#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

queues="${CELERY_QUEUES:-default,ingestion,embedding,apps_build,agent_runs,artifact_prod_interactive,artifact_prod_background,artifact_test}"
loglevel="${CELERY_LOG_LEVEL:-info}"
hostname="${CELERY_HOSTNAME:-worker@%h}"

args=(
  -m celery
  -A app.workers.celery_app.celery_app
  worker
  -Q "$queues"
  -n "$hostname"
  -l "$loglevel"
)

if [[ "${CELERY_ENABLE_BEAT:-0}" == "1" ]]; then
  args+=(--beat)
fi

exec python "${args[@]}"
