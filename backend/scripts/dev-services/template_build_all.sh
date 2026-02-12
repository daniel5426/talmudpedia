#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TEMPLATES_ROOT="$REPO_ROOT/backend/app/templates/published_apps"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required but not found in PATH." >&2
  exit 1
fi

failed=0

for template_dir in "$TEMPLATES_ROOT"/*; do
  if [[ ! -d "$template_dir" ]]; then
    continue
  fi
  template_key="$(basename "$template_dir")"

  if [[ ! -f "$template_dir/package.json" ]]; then
    echo "[template-build] skipping $template_key (missing package.json)"
    continue
  fi

  echo
  echo "[template-build] $template_key"
  cd "$template_dir"

  if [[ ! -d node_modules ]]; then
    echo "[template-build] installing dependencies for $template_key"
    npm install || failed=1
    if [[ "$failed" -ne 0 ]]; then
      echo "[template-build] install failed for $template_key"
      continue
    fi
  fi

  if ! npm run build; then
    echo "[template-build] build failed for $template_key"
    failed=1
  fi
done

if [[ "$failed" -ne 0 ]]; then
  echo
  echo "[template-build] one or more template builds failed."
  exit 1
fi

echo
echo "[template-build] all template builds passed."
