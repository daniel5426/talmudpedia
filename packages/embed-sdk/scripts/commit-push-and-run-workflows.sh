#!/usr/bin/env bash

set -euo pipefail

MESSAGE="${1:-chore(embed-sdk): trigger sdk workflows}"
REMOTE="${GIT_REMOTE:-talmudpedia}"
BRANCH="${GIT_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
FORCE_PUBLISH="${FORCE_PUBLISH:-false}"

git add -A

if git diff --cached --quiet; then
  git commit --allow-empty -m "${MESSAGE}"
else
  git commit -m "${MESSAGE}"
fi

git push "${REMOTE}" "${BRANCH}"

gh workflow run embed-sdk-ci.yml --ref "${BRANCH}"
gh workflow run embed-sdk-release.yml --ref "${BRANCH}" -f force_publish="${FORCE_PUBLISH}"
