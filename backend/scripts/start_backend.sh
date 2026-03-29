#!/usr/bin/env sh
set -eu

exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
