#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/danielbenassaya/Code/personal/talmudpedia"
BACKEND_DIR="$ROOT/backend"

# Ensure infra services are up (idempotent)
brew services start postgresql@17 >/dev/null 2>&1 || true
brew services start redis >/dev/null 2>&1 || true

# Start local S3-compatible endpoint (moto) only if not already listening
if ! lsof -iTCP:5001 -sTCP:LISTEN -nP >/dev/null 2>&1; then
  nohup /Users/danielbenassaya/Library/Python/3.12/bin/moto_server -H 127.0.0.1 -p 5001 > /tmp/talmudpedia-moto.log 2>&1 &
fi

# Start Celery worker only if not already running
if ! pgrep -f 'celery -A app.workers.celery_app.celery_app worker' >/dev/null 2>&1; then
  nohup bash -lc "set -a; source '$BACKEND_DIR/.env'; set +a; cd '$BACKEND_DIR' && /Library/Frameworks/Python.framework/Versions/3.12/bin/celery -A app.workers.celery_app.celery_app worker -Q apps_build,default,ingestion,embedding -l info" > /tmp/talmudpedia-celery.log 2>&1 &
fi

# Ensure S3 bucket exists in moto
python3 - <<'PY'
import boto3
s3 = boto3.client('s3', endpoint_url='http://127.0.0.1:5001', aws_access_key_id='test', aws_secret_access_key='test', region_name='us-east-1')
name='talmudpedia-apps-bundles'
existing=[b['Name'] for b in s3.list_buckets().get('Buckets',[])]
if name not in existing:
    s3.create_bucket(Bucket=name)
PY

# Start FastAPI (hot reload)
cd "$BACKEND_DIR"
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
