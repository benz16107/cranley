#!/usr/bin/env bash
# Build the site here and deploy it from the machine that is logged in to Vercel (benmac).
#
#   site/scripts/deploy.sh           a PREVIEW behind a Vercel login, with the slot notes on and search engines kept out
#   site/scripts/deploy.sh --prod    PRODUCTION: https://cranley.app. Needs Ben's yes each time.
#
# The site went public on 2026-11-14 (Ben, 8 pm). Project `cranley`; cranley.app and www.cranley.app are attached,
# with DNS at GoDaddy (A @ 216.150.1.1 and 216.150.16.1, CNAME www f6551f9cad87df1d.vercel-dns-016.com, set with
# `gddy dns` on macserver). The first production deployment was a one-line placeholder, because on this team a new
# project's first deployment becomes production; it is the rollback target:
#   on benmac:  vercel rollback cranley-iz8vdil4i-benz16107-1762s-projects.vercel.app --scope benz16107-1762s-projects
set -euo pipefail
cd "$(dirname "$0")/.."
host=${VERCEL_HOST:-benmac}; project=cranley; scope=benz16107-1762s-projects
remote=.cache/cranley-site
v="export PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH; vercel"
prod=; [ "${1:-}" = "--prod" ] && prod=1

if [ -n "$prod" ]; then
  PUBLIC_SLOT_LABELS=off PUBLIC_INDEX=1 pnpm build
  # the public site shows no empty picture frame and no slot note
  ! grep -rlE 'data-state="empty"|class="media hatch' dist || { echo "an empty picture frame is in the public build"; exit 1; }
else
  pnpm build
fi
pnpm check
cp vercel.json dist/vercel.json
printf '.env*\n' > dist/.vercelignore   # `vercel link` writes .env.local into the folder it deploys

ssh -o ConnectTimeout=10 "$host" "mkdir -p $remote/dist" || { echo "cannot reach $host; nothing was deployed"; exit 2; }
ssh "$host" "$v whoami" >/dev/null || { echo "$host is not logged in to Vercel; nothing was deployed"; exit 2; }
rsync -a --delete --exclude .vercel dist/ "$host:$remote/dist/"
ssh "$host" "cd $remote/dist && $v link --yes --project $project --scope $scope" >/dev/null 2>&1

if [ -n "$prod" ]; then
  ssh "$host" "cd $remote/dist && $v deploy --yes --prod --scope $scope" | tail -3
  echo
  sleep 5
  [ "$(curl -s https://cranley.app/ | grep -c 'data-slot="hero-loop"')" = 1 ] || { echo "https://cranley.app does not serve the home page"; exit 1; }
  echo "live: https://cranley.app  ($(curl -s -o /dev/null -w 'HTTP %{http_code}' https://cranley.app/docs/); www answers $(curl -s -o /dev/null -w '%{http_code}' https://www.cranley.app/))"
else
  url=$(ssh "$host" "cd $remote/dist && $v deploy --yes --target=preview --scope $scope" | grep -o 'https://[a-z0-9-]*\.vercel\.app' | head -1)
  code=$(curl -s -o /dev/null -w '%{http_code}' "$url/")
  echo "preview: $url  (logged out: HTTP $code, want 302 or 401)"
  [ "$code" = 302 ] || [ "$code" = 401 ] || { echo "the preview answered without a login"; exit 1; }
fi
