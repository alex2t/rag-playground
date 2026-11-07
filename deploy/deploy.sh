#!/usr/bin/env bash
# Deploy one release image to one environment (D33, D34): deploy/deploy.sh <git-sha> <staging|prod>
# Rollback: run it again with the previous SHA.
# Doppler: each environment's service token is scoped to /srv/rag-playground/<env>
#   (echo <token> | doppler configure set token --scope /srv/rag-playground/<env>),
# so doppler run started there injects that environment's secrets (D32).
set -euo pipefail

usage="usage: deploy.sh <git-sha> <staging|prod>"
sha=${1:?$usage}
env=${2:?$usage}
case "$env" in
  prod) port=8000 ;;
  staging) port=8001 ;;
  *) echo "environment must be staging or prod, got: $env" >&2; exit 2 ;;
esac
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "git SHA must be the full 40 characters, got: $sha" >&2; exit 2; }

compose_file="$(cd "$(dirname "$0")" && pwd)/docker-compose.yml"
project="rag-playground-$env"
export APP_IMAGE="ghcr.io/alex2t/rag-playground:$sha" APP_PORT=$port

docker pull "$APP_IMAGE"
cd "${SCOPE_ROOT:-/srv/rag-playground}/$env"
doppler run -- docker compose -f "$compose_file" -p "$project" up -d --no-build --pull never

echo "waiting for $project to answer on port $port as $sha"
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
  health=$(curl -sS --max-time 5 "http://127.0.0.1:$port/api/health" 2>/dev/null || true)
  if [[ "$health" == *'"status":"ok"'* && "$health" == *"\"version\":\"$sha\""* ]]; then
    echo "deployed: $health"
    exit 0
  fi
  sleep 2
done
echo "not healthy after 180 s, last answer: ${health:-none}" >&2
docker compose -f "$compose_file" -p "$project" logs --tail 50 app >&2
exit 1
