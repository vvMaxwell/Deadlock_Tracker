#!/usr/bin/env bash
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-/opt/deadlock-tracker}"
REPO_URL="${REPO_URL:-https://github.com/vvMaxwell/Deadlock_Tracker.git}"
BRANCH="${BRANCH:-main}"

mkdir -p "${DEPLOY_PATH}"
cd "${DEPLOY_PATH}"

if [[ ! -d .git ]]; then
  find "${DEPLOY_PATH}" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  git clone --branch "${BRANCH}" "${REPO_URL}" .
else
  git fetch origin "${BRANCH}"
  git checkout "${BRANCH}"
  git pull --ff-only origin "${BRANCH}"
fi

mkdir -p deploy
if [[ ! -f deploy/app.env ]]; then
  cp deploy/app.env.example deploy/app.env
fi

docker compose -f deploy/docker-compose.yml up -d --build --remove-orphans
docker image prune -f

echo "Deployment complete."
