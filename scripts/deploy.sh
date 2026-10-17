#!/usr/bin/env bash
# Deploy the latest main to production. Run ON THE SERVER, e.g. from your machine:
#
#   ssh -i ~/.ssh/cobbra_hetzner root@cobbra.app /home/cobbra/cobbra/scripts/deploy.sh
#
#   deploy.sh              fetch origin/main, rebuild only the services whose files changed
#   deploy.sh --dry-run    show what would be deployed, change nothing
#   deploy.sh --rollback   go back to the commit that was live before the last deploy
#
# Needs a read-only GitHub deploy key on the server (DEPLOY.md §8). Postgres is never
# rebuilt or restarted by this script.

# The whole script is one { ... } block so bash parses it completely before running:
# `git reset` below replaces this very file, and bash otherwise reads scripts lazily.
{
set -euo pipefail

cd "$(dirname "$0")/.."
BRANCH="${DEPLOY_BRANCH:-main}"
STATE_DIR=.deploy                       # git-ignored: last/previous live commit + history
COMPOSE=(docker compose -f docker-compose.prod.yml --env-file .env.prod)

say()  { printf '\033[1m[deploy]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[deploy] ERROR:\033[0m %s\n' "$*" >&2; exit 1; }

DRY_RUN=0; ROLLBACK=0
for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=1 ;;
    --rollback) ROLLBACK=1 ;;
    -h|--help)  sed -n '2,13p' "$0"; exit 0 ;;
    *) die "unknown option: $arg" ;;
  esac
done

# One deploy at a time.
exec 9>/tmp/cobbra-deploy.lock
flock -n 9 || die "another deploy is already running"

[ -f .env.prod ] || die ".env.prod not found in $(pwd)"
DOMAIN="$(grep -E '^DOMAIN=' .env.prod | cut -d= -f2- | tr -d '\r"'"'"' ')"
[ -n "$DOMAIN" ] || die "DOMAIN is not set in .env.prod"

# Never overwrite changes made directly on the server: they would be lost silently.
if ! git diff --quiet HEAD -- || ! git diff --cached --quiet; then
  git status --short --untracked-files=no
  die "the server has uncommitted changes to tracked files (above). Commit them to the repo or discard them first."
fi

OLD="$(git rev-parse HEAD)"
if [ "$ROLLBACK" = 1 ]; then
  [ -f "$STATE_DIR/previous" ] || die "no previous deploy recorded — nothing to roll back to"
  NEW="$(cat "$STATE_DIR/previous")"
  say "Rolling back to $(git log -1 --format='%h %s' "$NEW")"
else
  say "Fetching origin/$BRANCH ..."
  git fetch --quiet origin "$BRANCH"
  NEW="$(git rev-parse "origin/$BRANCH")"
fi

if [ "$OLD" = "$NEW" ]; then
  say "Already live: $(git log -1 --format='%h %s' "$NEW"). Nothing to do."
  exit 0
fi

CHANGED="$(git diff --name-only "$OLD" "$NEW")"
say "Live:     $(git log -1 --format='%h %s' "$OLD")"
say "Deploying $(git log -1 --format='%h %s' "$NEW")"
git --no-pager log --oneline --no-decorate "$OLD..$NEW" 2>/dev/null | sed 's/^/           /' || true

# Which services need rebuilding / recreating?
SERVICES=()
grep -q '^backend/'  <<<"$CHANGED" && SERVICES+=(backend)
grep -q '^frontend/' <<<"$CHANGED" && SERVICES+=(frontend)
grep -q '^nginx/'    <<<"$CHANGED" && SERVICES+=(nginx)
if grep -qx 'docker-compose.prod.yml' <<<"$CHANGED"; then
  # Recreate every app service; compose leaves the ones whose config didn't change alone.
  SERVICES=(backend frontend nginx certbot)
  say "docker-compose.prod.yml changed. postgres is NOT touched by this script; if its"
  say "service definition changed, recreate it yourself after taking a backup."
fi
mapfile -t SERVICES < <(printf '%s\n' "${SERVICES[@]}" | awk 'NF && !seen[$0]++')
BUILD=()
for s in "${SERVICES[@]}"; do case "$s" in backend|frontend) BUILD+=("$s") ;; esac; done

if [ "${#SERVICES[@]}" = 0 ]; then
  say "No service files changed (docs/scripts only) — updating the checkout only."
else
  say "Services:  ${SERVICES[*]}   (rebuild: ${BUILD[*]:-none})"
fi

if [ "$DRY_RUN" = 1 ]; then
  say "Dry run — nothing changed."
  exit 0
fi

mkdir -p "$STATE_DIR"
git reset --quiet --hard "$NEW"
restore() { say "Restoring checkout to $(git rev-parse --short "$OLD") — running containers were not changed."; git reset --quiet --hard "$OLD"; }

# Check everything that can fail *before* touching running containers.
if printf '%s\n' "${SERVICES[@]}" | grep -qx nginx; then
  say "Testing nginx config ..."
  if ! "${COMPOSE[@]}" run --rm --no-deps --entrypoint /bin/sh nginx \
       -c 'envsubst "\$DOMAIN" < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && nginx -t -q'; then
    restore; die "nginx config test failed"
  fi
fi
if [ "${#BUILD[@]}" -gt 0 ]; then
  say "Building ${BUILD[*]} ..."
  "${COMPOSE[@]}" build "${BUILD[@]}" || { restore; die "image build failed"; }
fi

# The backend runs `alembic upgrade head` on startup: snapshot the database first.
if printf '%s\n' "${SERVICES[@]}" | grep -qx backend && [ -x ./backup.sh ]; then
  say "Backing up the database before the backend restarts ..."
  ./backup.sh || { restore; die "database backup failed — deploy aborted"; }
fi

if [ "${#SERVICES[@]}" -gt 0 ]; then
  say "Replacing ${SERVICES[*]} ..."
  "${COMPOSE[@]}" up -d --no-deps "${SERVICES[@]}"
fi

echo "$OLD" > "$STATE_DIR/previous"
echo "$NEW" > "$STATE_DIR/last"
echo "$(date -Is) $(git rev-parse --short "$OLD") -> $(git rev-parse --short "$NEW") [${SERVICES[*]:-none}]$([ "$ROLLBACK" = 1 ] && echo ' ROLLBACK')" >> "$STATE_DIR/history.log"

# The site must answer through nginx (TLS + proxy + backend).
say "Checking https://$DOMAIN ..."
for i in $(seq 1 30); do
  if curl -fsS -o /dev/null --max-time 5 "https://$DOMAIN/" && \
     curl -fsS -o /dev/null --max-time 5 "https://$DOMAIN/api/auth/setup"; then
    say "Live and healthy: $(git log -1 --format='%h %s' "$NEW")"
    docker image prune -f >/dev/null 2>&1 || true      # drop the superseded images
    exit 0
  fi
  sleep 2
done
"${COMPOSE[@]}" logs --tail=40 backend || true
die "https://$DOMAIN is not answering after the deploy. Check the logs above; to go back run: $0 --rollback"
}
