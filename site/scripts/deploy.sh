#!/usr/bin/env bash
# Build the site here and deploy it as a Vercel PREVIEW from the machine that is logged in to Vercel.
#
#   site/scripts/deploy.sh                 preview, slot notes on, search engines kept out
#   VERCEL_HOST=benmac site/scripts/deploy.sh
#
# Why a preview: on this Vercel team a new project's first deployment becomes production, and the production domain
# is public while preview URLs sit behind a Vercel login. So the first run puts a one-line placeholder in the
# production slot, and the site itself only ever goes up with --target=preview. Going public is a separate step
# that waits for a yes (see the end of this file).
set -euo pipefail
cd "$(dirname "$0")/.."
host=${VERCEL_HOST:-benmac}; project=cranley; scope=benz16107-1762s-projects
remote=.cache/cranley-site
v="export PATH=/opt/homebrew/bin:/usr/local/bin:\$PATH; vercel"

pnpm build
pnpm check
cp vercel.json dist/vercel.json
printf '.env*\n' > dist/.vercelignore   # `vercel link` writes .env.local into the folder it deploys

ssh -o ConnectTimeout=10 "$host" "mkdir -p $remote/dist $remote/placeholder" || { echo "cannot reach $host; nothing was deployed"; exit 2; }
ssh "$host" "$v whoami" >/dev/null || { echo "$host is not logged in to Vercel; nothing was deployed"; exit 2; }

# First run only: the project, and a placeholder that takes the production slot.
if ! ssh "$host" "$v project ls --scope $scope 2>&1" | grep -qw "$project"; then
  ssh "$host" "cd $remote/placeholder && printf '<!doctype html><meta charset=utf-8><meta name=robots content=noindex><title>Cranley</title><p>Cranley. Coming soon.' > index.html \
    && printf '{\"git\":{\"deploymentEnabled\":false}}' > vercel.json \
    && $v project add $project --scope $scope && $v link --yes --project $project --scope $scope && $v deploy --yes --prod --scope $scope"
fi

rsync -a --delete --exclude .vercel dist/ "$host:$remote/dist/"
url=$(ssh "$host" "cd $remote/dist && $v link --yes --project $project --scope $scope >/dev/null 2>&1 && $v deploy --yes --target=preview --scope $scope" | tail -1)
echo "preview: $url"

# Logged out, the preview must send us to a login and no project domain may serve the site.
code=$(curl -s -o /dev/null -w '%{http_code}' "$url/")
echo "preview logged out: HTTP $code (want 302 or 401)"
for d in $(ssh "$host" "$v api /v9/projects/$project/domains --scope $scope" | grep -o '"name": *"[^"]*"' | cut -d'"' -f4); do
  hit=$(curl -sL "https://$d/" | grep -c 'The listing says' || true)
  echo "domain $d: $([ "$hit" = 0 ] && echo 'does not serve the site' || echo 'SERVES THE SITE')"
  [ "$hit" = 0 ] || exit 1
done
[ "$code" = 302 ] || [ "$code" = 401 ] || { echo "the preview answered without a login"; exit 1; }

# Going public, only after Ben's yes. Run by hand; nothing above does it.
#   1. here:        PUBLIC_SLOT_LABELS=off PUBLIC_INDEX=1 pnpm build && pnpm check && cp vercel.json dist/ && printf '.env*\n' > dist/.vercelignore
#                   rsync -a --delete --exclude .vercel dist/ $host:$remote/dist/
#   2. on $host:    cd ~/$remote/dist && vercel deploy --yes --prod --scope $scope        (replaces the placeholder on cranley.vercel.app)
#                   vercel domains add cranley.app $project --scope $scope && vercel domains add www.cranley.app $project --scope $scope
#                   vercel domains inspect cranley.app --scope $scope                     (prints the A and CNAME values to use below)
#   3. on macserver (the records today: A @ "Parked", CNAME www -> cranley.app; delete then add, because `dns set` fails on a CNAME):
#                   gddy dns delete cranley.app --type A --name @ --timeout 40s
#                   gddy dns add cranley.app --type A --name @ --data <A value from Vercel> --timeout 40s
#                   gddy dns delete cranley.app --type CNAME --name www --timeout 40s
#                   gddy dns add cranley.app --type CNAME --name www --data <CNAME value from Vercel> --timeout 40s
#   4. check:       curl -sI https://cranley.app/ | head -1; curl -sI https://www.cranley.app/ | grep -i location
#   Undo:           on $host, vercel rollback <the placeholder deployment's URL> --scope $scope  (under a minute; DNS can stay)
