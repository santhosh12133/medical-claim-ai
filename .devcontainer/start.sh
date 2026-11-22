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

# Demo setting: clean claims are approved automatically; anything flagged goes to the admin review queue.
# OPENAI_API_KEY / ANTHROPIC_API_KEY (add them as Codespaces secrets) switch on GPT/Claude.
sudo --preserve-env=OPENAI_API_KEY,ANTHROPIC_API_KEY bash deploy/setup-server.sh --origin "$ORIGIN" --app-dir "$PWD" \
  --no-update --no-firewall --no-swap --no-backups --auto-decisions on --admin-email admin@demo.local --employee-email employee@demo.local --employee-name "Employee Demo" \
  2>&1 | tee /tmp/medical-claim-ai-start.log

cat <<INFO

==================================================================
 Medical Claim AI is running at:  $ORIGIN

 Logins (generated for this codespace):
$(sudo sed 's/^/   /' /root/medical-claim-ai-credentials.txt)

 Automatic decisions: $(sudo grep -q '^AUTO_DECISION_ENABLED=true' .env && echo "ON (clean claims approved; flagged ones go to admin review)" || echo "OFF")
 GPT/Claude check:    $(sudo grep -q '^GPT_DECISION_ENABLED=true' .env && echo "ON" || echo "OFF (add an OPENAI_API_KEY Codespaces secret to switch it on)")

 To share the link: open the PORTS tab, right-click port 80,
 choose "Port Visibility" -> "Public".
 Stop the codespace when you're done, to save free hours.
==================================================================
INFO
