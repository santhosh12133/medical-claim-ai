#!/usr/bin/env bash
# Starts the full app inside a GitHub Codespace (runs automatically on every codespace start).
# The first start builds the images (about 10 minutes); later starts take about a minute.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -n "${CODESPACE_NAME:-}" ]; then
  ORIGIN="https://${CODESPACE_NAME}-80.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
else
  ORIGIN="${MCA_ORIGIN:-http://localhost}"
fi

for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done  # Docker starts with the codespace
docker info >/dev/null 2>&1 || { echo "Docker is not running in this codespace; rebuild the container"; exit 1; }

sudo bash deploy/setup-server.sh --origin "$ORIGIN" --app-dir "$PWD" --no-update --no-firewall --no-swap \
  --no-backups --admin-email admin@demo.local --employee-email employee@demo.local --employee-name "Employee Demo" \
  2>&1 | tee /tmp/medical-claim-ai-start.log

cat <<INFO

==================================================================
 Medical Claim AI is running at:  $ORIGIN

 Logins (generated for this codespace):
$(sudo sed 's/^/   /' /root/medical-claim-ai-credentials.txt)

 To share the link: open the PORTS tab, right-click port 80,
 choose "Port Visibility" -> "Public".
 Stop the codespace when you're done, to save free hours.
==================================================================
INFO
