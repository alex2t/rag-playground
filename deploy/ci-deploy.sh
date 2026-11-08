#!/usr/bin/env bash
# The only command GitHub's deploy key may run on the VPS (D36). Installed outside the checkout it updates, so a
# deploy can never rewrite the script while it runs:
#   install -m 755 /srv/rag-playground/deploy/ci-deploy.sh /usr/local/bin/rag-playground-deploy
# and forced on the key in /root/.ssh/authorized_keys:
#   command="/usr/local/bin/rag-playground-deploy",restrict ssh-ed25519 AAAA... github-deploy
# The workflow sends the commit's full SHA as the SSH command; it is the only input, checked before any use.
set -euo pipefail

sha=${SSH_ORIGINAL_COMMAND:-}
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo "expected a full 40-character git SHA, got: $sha" >&2; exit 2; }

repo=/srv/rag-playground
git -C "$repo" fetch --quiet origin main
git -C "$repo" checkout --quiet --detach "$sha"
exec bash "$repo/deploy/deploy.sh" "$sha"
