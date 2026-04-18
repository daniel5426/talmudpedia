#!/usr/bin/env bash
set -euo pipefail

export HOME="/tmp/crawl4ai-home"
export XDG_CACHE_HOME="/tmp/crawl4ai-cache"
export XDG_CONFIG_HOME="/tmp/crawl4ai-config"
export XDG_DATA_HOME="/tmp/crawl4ai-data"
export CRAWL4AI_DB_PATH="$XDG_DATA_HOME/crawl4ai.db"
export PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
export GUNICORN_CMD_ARGS="${GUNICORN_CMD_ARGS:-} --worker-tmp-dir /tmp"

mkdir -p "$HOME" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME" "$XDG_DATA_HOME"

supervisord &

for _ in $(seq 1 60); do
  if bash -lc '>/dev/tcp/127.0.0.1/11235' 2>/dev/null; then
    break
  fi
  sleep 1
done

exec socat "TCP-LISTEN:${PORT:-8080},fork,reuseaddr" TCP:127.0.0.1:11235
