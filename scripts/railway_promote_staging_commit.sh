#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/railway_promote_staging_commit.sh <commit-sha> [--skip-staging-check]

Promotes the same tested commit from staging to production for:
  - backend
  - frontend
  - backend-worker
  - docs-site
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

commit_sha="$1"
shift

skip_staging_check=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-staging-check)
      skip_staging_check=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

for cmd in railway jq curl; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "Missing required command: $cmd" >&2
    exit 1
  }
done

token="$(jq -r '.user.token // empty' "$HOME/.railway/config.json")"
if [[ -z "$token" ]]; then
  echo "Railway token not found. Run: railway login" >&2
  exit 1
fi

project_id="$(railway status --json | jq -r '.id')"
if [[ -z "$project_id" || "$project_id" == "null" ]]; then
  echo "Could not resolve Railway project id from the linked repo." >&2
  exit 1
fi

query='query ProjectSnapshot($projectId: String!) {
  project(id: $projectId) {
    environments {
      edges {
        node {
          name
          id
          serviceInstances {
            edges {
              node {
                serviceName
                serviceId
                latestDeployment {
                  status
                  meta
                }
              }
            }
          }
        }
      }
    }
  }
}'

snapshot="$(
  jq -n --arg query "$query" --arg projectId "$project_id" \
    '{query:$query,variables:{projectId:$projectId}}' \
  | curl -fsS https://backboard.railway.com/graphql/v2 \
      -H "Authorization: Bearer $token" \
      -H 'Content-Type: application/json' \
      --data @-
)"

services=(backend frontend backend-worker docs-site)
staging_env_id="$(jq -r '.data.project.environments.edges[] | select(.node.name=="staging") | .node.id' <<<"$snapshot")"
prod_env_id="$(jq -r '.data.project.environments.edges[] | select(.node.name=="production") | .node.id' <<<"$snapshot")"

if [[ -z "$staging_env_id" || -z "$prod_env_id" ]]; then
  echo "Could not resolve staging/production environments in Railway." >&2
  exit 1
fi

mutation='mutation Promote($environmentId: String!, $serviceId: String!, $commitSha: String!) {
  serviceInstanceDeployV2(environmentId: $environmentId, serviceId: $serviceId, commitSha: $commitSha)
}'

for service in "${services[@]}"; do
  staging_status="$(jq -r --arg service "$service" '.data.project.environments.edges[] | select(.node.name=="staging") | .node.serviceInstances.edges[] | select(.node.serviceName==$service) | .node.latestDeployment.status // empty' <<<"$snapshot")"
  staging_commit="$(jq -r --arg service "$service" '.data.project.environments.edges[] | select(.node.name=="staging") | .node.serviceInstances.edges[] | select(.node.serviceName==$service) | .node.latestDeployment.meta.commitHash // empty' <<<"$snapshot")"
  prod_service_id="$(jq -r --arg service "$service" '.data.project.environments.edges[] | select(.node.name=="production") | .node.serviceInstances.edges[] | select(.node.serviceName==$service) | .node.serviceId' <<<"$snapshot")"

  if [[ -z "$prod_service_id" || "$prod_service_id" == "null" ]]; then
    echo "Missing production service instance for $service" >&2
    exit 1
  fi

  if [[ "$skip_staging_check" -ne 1 ]]; then
    if [[ "$staging_status" != "SUCCESS" ]]; then
      echo "Staging service $service is not healthy. Current status: ${staging_status:-missing}" >&2
      exit 1
    fi
    if [[ "$staging_commit" != "$commit_sha" ]]; then
      echo "Staging service $service is on $staging_commit, expected $commit_sha" >&2
      exit 1
    fi
  fi

  deployment_id="$(
    jq -n \
      --arg query "$mutation" \
      --arg environmentId "$prod_env_id" \
      --arg serviceId "$prod_service_id" \
      --arg commitSha "$commit_sha" \
      '{query:$query,variables:{environmentId:$environmentId,serviceId:$serviceId,commitSha:$commitSha}}' \
    | curl -fsS https://backboard.railway.com/graphql/v2 \
        -H "Authorization: Bearer $token" \
        -H 'Content-Type: application/json' \
        --data @- \
    | jq -r '.data.serviceInstanceDeployV2'
  )"

  echo "$service -> $deployment_id"
done
