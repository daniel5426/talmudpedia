#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

ENV_FILE="${TALMUDPEDIA_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]]; then
  if [[ -f "$BACKEND_DIR/.env.test" ]]; then
    ENV_FILE="$BACKEND_DIR/.env.test"
  else
    ENV_FILE="$BACKEND_DIR/.env.test.example"
  fi
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing backend test env file: $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

export TALMUDPEDIA_ENV_FILE="$ENV_FILE"
export TALMUDPEDIA_ENV_PROFILE="${TALMUDPEDIA_ENV_PROFILE:-test}"

python3 - <<'PY'
import os
import socket
import sys
from urllib.parse import urlparse


def check_socket(name: str, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            print(f"[ok] {name}: {host}:{port}")
            return True
    except OSError:
        print(f"[missing] {name}: {host}:{port}")
        return False


def db_host_port() -> tuple[str, int]:
    raw = (
        os.getenv("DATABASE_URL_LOCAL")
        or os.getenv("DATABASE_URL")
        or f"postgresql://{os.getenv('LOCAL_POSTGRES_HOST', '127.0.0.1')}:{os.getenv('LOCAL_POSTGRES_PORT', '5432')}"
    )
    parsed = urlparse(raw)
    host = parsed.hostname or os.getenv("LOCAL_POSTGRES_HOST", "127.0.0.1")
    port = parsed.port or int(os.getenv("LOCAL_POSTGRES_PORT", "5432"))
    return host, port


def redis_host_port() -> tuple[str, int]:
    parsed = urlparse(os.getenv("REDIS_URL", "redis://127.0.0.1:6379/15"))
    return parsed.hostname or "127.0.0.1", parsed.port or 6379


checks = [
    ("postgres", *db_host_port()),
    ("redis", *redis_host_port()),
]

failures = 0
for name, host, port in checks:
    if not check_socket(name, host, port):
        failures += 1

if failures:
    sys.exit(1)
PY
