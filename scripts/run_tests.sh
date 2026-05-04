#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env.test ]; then
  echo "Missing .env.test file"
  exit 1
fi

set -a
. ./.env.test
set +a

docker compose up -d

python -m pytest
