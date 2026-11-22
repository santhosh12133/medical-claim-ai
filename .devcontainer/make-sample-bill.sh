#!/usr/bin/env bash
# Writes sample-bill.png (a synthetic bill for "Employee Demo") into the workspace; download it from the file
# explorer (right-click -> Download) and upload it on the employee page.
set -euo pipefail
cd "$(dirname "$0")/.."
C=(sudo docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml)
"${C[@]}" exec -T api python scripts/stack_smoke_test.py --make-bill /app/logs/sample-bill.png >/dev/null
"${C[@]}" cp api:/app/logs/sample-bill.png ./sample-bill.png
sudo chown "$(id -u):$(id -g)" sample-bill.png
echo "Wrote $(pwd)/sample-bill.png"
