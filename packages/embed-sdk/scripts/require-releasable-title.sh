#!/usr/bin/env bash

set -euo pipefail

MODE="${1:?mode must be 'push' or 'pr'}"
BASE_REF="${2:-}"
HEAD_REF="${3:-HEAD}"
TITLE="${4:-}"

if [[ -z "${BASE_REF}" ]]; then
  echo "Base ref is required."
  exit 1
fi

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "${ROOT_DIR}"

if git diff --quiet "${BASE_REF}" "${HEAD_REF}" -- packages/embed-sdk; then
  echo "No embed-sdk package changes detected in ${BASE_REF}..${HEAD_REF}; skipping releasable title check."
  exit 0
fi

case "${MODE}" in
  pr)
    CANDIDATE="${TITLE}"
    LABEL="PR title"
    ;;
  push)
    CANDIDATE="$(git log -1 --pretty=%s "${HEAD_REF}")"
    LABEL="merge commit title"
    ;;
  *)
    echo "Unsupported mode: ${MODE}"
    exit 1
    ;;
esac

PATTERN='^(feat|fix)(\(embed-sdk\))?!?: .+'

if [[ "${CANDIDATE}" =~ ${PATTERN} ]]; then
  echo "embed-sdk release title check passed: ${CANDIDATE}"
  exit 0
fi

cat <<EOF
embed-sdk package files changed, but the ${LABEL} is not release-please-releasable:
  ${CANDIDATE}

Use a conventional title such as:
  feat(embed-sdk): add runtime attachment support
  fix(embed-sdk): handle deleted thread history correctly

Without that, release-please completes successfully but does not open a release PR.
EOF

exit 1
