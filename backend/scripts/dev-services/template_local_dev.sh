#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEMPLATES_ROOT="$REPO_ROOT/backend/app/templates/published_apps"

HOST="127.0.0.1"
PORT="4173"
INSTALL_MODE="auto"
RUN_BUILD_CHECK="0"
TEMPLATE_KEY=""

usage() {
  cat <<'EOF'
Usage:
  backend/scripts/dev-services/template_local_dev.sh <template-key> [options]

Examples:
  backend/scripts/dev-services/template_local_dev.sh chat-classic
  backend/scripts/dev-services/template_local_dev.sh chat-grid --port 4174 --host 0.0.0.0
  backend/scripts/dev-services/template_local_dev.sh chat-classic --build-check

Options:
  --host <host>       Vite dev server host (default: 127.0.0.1)
  --port <port>       Vite dev server port (default: 4173)
  --install           Force npm install before dev
  --ci                Force npm ci before dev (requires package-lock.json)
  --skip-install      Skip dependency install even if node_modules is missing
  --build-check       Run npm run build before starting dev server
  -h, --help          Show this message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --port)
      PORT="${2:-}"
      shift 2
      ;;
    --install)
      INSTALL_MODE="install"
      shift
      ;;
    --ci)
      INSTALL_MODE="ci"
      shift
      ;;
    --skip-install)
      INSTALL_MODE="skip"
      shift
      ;;
    --build-check)
      RUN_BUILD_CHECK="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      if [[ -n "$TEMPLATE_KEY" ]]; then
        echo "Only one template key is allowed." >&2
        usage
        exit 1
      fi
      TEMPLATE_KEY="$1"
      shift
      ;;
  esac
done

if [[ -z "$TEMPLATE_KEY" ]]; then
  echo "Missing template key." >&2
  usage
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found in PATH." >&2
  exit 1
fi

TEMPLATE_DIR="$TEMPLATES_ROOT/$TEMPLATE_KEY"
if [[ ! -d "$TEMPLATE_DIR" ]]; then
  echo "Template not found: $TEMPLATE_DIR" >&2
  echo "Available templates:" >&2
  find "$TEMPLATES_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort >&2
  exit 1
fi

if [[ ! -f "$TEMPLATE_DIR/package.json" ]]; then
  echo "Template is missing package.json: $TEMPLATE_DIR" >&2
  exit 1
fi

cd "$TEMPLATE_DIR"

case "$INSTALL_MODE" in
  auto)
    if [[ ! -d node_modules ]]; then
      echo "[template-dev] node_modules not found; running npm install"
      npm install
    else
      # npm optional dependency installs occasionally miss Rollup native packages.
      # Preflight Rollup load so local dev is resilient to npm/cli optional-deps bug.
      if ! node -e "require('rollup')" >/dev/null 2>&1; then
        echo "[template-dev] repairing optional dependencies (npm install --include=optional)"
        npm install --include=optional
      fi
    fi
    ;;
  install)
    echo "[template-dev] running npm install"
    npm install
    ;;
  ci)
    if [[ ! -f package-lock.json ]]; then
      echo "Cannot run npm ci: package-lock.json is missing in $TEMPLATE_DIR" >&2
      exit 1
    fi
    echo "[template-dev] running npm ci"
    npm ci
    ;;
  skip)
    echo "[template-dev] skipping dependency install"
    ;;
  *)
    echo "Unsupported install mode: $INSTALL_MODE" >&2
    exit 1
    ;;
esac

if [[ "$RUN_BUILD_CHECK" == "1" ]]; then
  echo "[template-dev] running build check (npm run build)"
  npm run build
fi

echo "[template-dev] starting $TEMPLATE_KEY on http://$HOST:$PORT"
exec npm run dev -- --host "$HOST" --port "$PORT"
