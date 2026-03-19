#!/usr/bin/env bash

set -euo pipefail

MESSAGE="${1:-chore(embed-sdk): trigger sdk workflows}"
REMOTE="${GIT_REMOTE:-talmudpedia}"
BRANCH="${GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
FORCE_PUBLISH="${FORCE_PUBLISH:-false}"

PACKAGE_CHANGED=false
if ! git diff --quiet -- packages/embed-sdk; then
  PACKAGE_CHANGED=true
fi
if ! git diff --cached --quiet -- packages/embed-sdk; then
  PACKAGE_CHANGED=true
fi

git add -A

if git diff --cached --quiet; then
  git commit --allow-empty -m "${MESSAGE}"
else
  git commit -m "${MESSAGE}"
fi

git push "${REMOTE}" "${BRANCH}"

gh workflow run embed-sdk-ci.yml --ref "${BRANCH}"

if [[ "${BRANCH}" == "main" && "${PACKAGE_CHANGED}" == "true" && "${FORCE_PUBLISH}" != "true" ]]; then
  echo "Skipping manual embed-sdk-release dispatch because the push to main already triggers it."
  exit 0
fi

gh workflow run embed-sdk-release.yml --ref "${BRANCH}" -f force_publish="${FORCE_PUBLISH}"
