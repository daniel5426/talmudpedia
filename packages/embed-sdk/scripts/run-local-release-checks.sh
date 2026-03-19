#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "[1/3] embed-sdk package checks"
cd "${REPO_ROOT}/packages/embed-sdk"
npm ci
npm run build
npm run smoke:pack
npm pack --dry-run

echo "[2/3] frontend embed-sdk tests"
cd "${REPO_ROOT}/frontend-reshet"
rm -rf node_modules
pnpm install --frozen-lockfile
pnpm exec jest --runInBand src/__tests__/embed_sdk/embedded_agent_sdk.test.ts

echo "[3/3] backend embed runtime tests"
cd "${REPO_ROOT}/backend"
python3 -m pip install -r requirements.txt -r requirements-dev.txt
PYTHONPATH=. pytest -q tests/embedded_agent_runtime/test_embedded_agent_runtime_api.py

echo "embed-sdk local release checks passed"
