#!/usr/bin/env bash
set -euo pipefail

supervisord &

for _ in $(seq 1 60); do
  if bash -lc '>/dev/tcp/127.0.0.1/11235' 2>/dev/null; then
    break
  fi
  sleep 1
done

exec socat "TCP-LISTEN:${PORT:-8080},fork,reuseaddr" TCP:127.0.0.1:11235
