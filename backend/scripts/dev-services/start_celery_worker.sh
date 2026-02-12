#!/usr/bin/env bash
set -euo pipefail
cd /Users/danielbenassaya/Code/personal/talmudpedia/backend
set -a
source .env
set +a
exec /Library/Frameworks/Python.framework/Versions/3.12/bin/celery -A app.workers.celery_app.celery_app worker -Q apps_build,default,ingestion,embedding -l info
