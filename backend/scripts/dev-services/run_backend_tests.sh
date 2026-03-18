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
export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT_DIR"

if [[ "$#" -eq 0 ]]; then
  set -- backend/tests
fi

exec python3 -m pytest "$@"
