#!/usr/bin/env bash
# Forced command for the GitHub Actions deploy key. In /root/.ssh/authorized_keys:
#
#   restrict,command="/home/cobbra/cobbra/scripts/deploy-ssh-gate.sh" ssh-ed25519 AAAA... github-actions-deploy
#
# Whatever command the client asks for arrives in $SSH_ORIGINAL_COMMAND; only these
# three are allowed, so the key can run a deploy but never get a shell.
set -euo pipefail
DEPLOY="$(dirname "$0")/deploy.sh"

case "${SSH_ORIGINAL_COMMAND:-deploy}" in
  deploy)   exec "$DEPLOY" ;;
  dry-run)  exec "$DEPLOY" --dry-run ;;
  rollback) exec "$DEPLOY" --rollback ;;
  *)
    echo "deploy-ssh-gate: '${SSH_ORIGINAL_COMMAND}' is not allowed (use: deploy, dry-run, rollback)" >&2
    exit 2
    ;;
esac
