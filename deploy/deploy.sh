#!/usr/bin/env bash
# Deploy one release image to prod (D34, D35: prod only): deploy/deploy.sh <git-sha>
# Rollback: run it again with the previous SHA.
# Doppler: the prod service token is scoped to /srv/rag-playground
#   (echo <token> | doppler configure set token --scope /srv/rag-playground),
# so doppler run started there injects prod's secrets (D32).
set -euo pipefail

sha=${1:?usage: deploy.sh <git-sha>}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "git SHA must be the full 40 characters, got: $sha" >&2; exit 2; }

compose_file="$(cd "$(dirname "$0")" && pwd)/docker-compose.yml"
project=rag-playground-prod
export APP_IMAGE="ghcr.io/alex2t/rag-playground:$sha"

docker pull "$APP_IMAGE"
cd "${SCOPE_ROOT:-/srv/rag-playground}"
doppler run -- docker compose -f "$compose_file" -p "$project" up -d --no-build --pull never

echo "waiting for $project to answer on port 8000 as $sha"
deadline=$((SECONDS + 180))
while (( SECONDS < deadline )); do
  health=$(curl -sS --max-time 5 "http://127.0.0.1:8000/api/health" 2>/dev/null || true)
  if [[ "$health" == *'"status":"ok"'* && "$health" == *"\"version\":\"$sha\""* ]]; then
    echo "deployed: $health"
    exit 0
  fi
  sleep 2
done
echo "not healthy after 180 s, last answer: ${health:-none}" >&2
docker compose -f "$compose_file" -p "$project" logs --tail 50 app >&2
exit 1
