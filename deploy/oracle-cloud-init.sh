#!/bin/bash
# Medical Claim AI: installs itself on the server's first boot. No SSH or terminal needed.
#
# Oracle Cloud: Create instance -> "Show advanced options" -> "Management" ->
# "Initialization script" -> "Paste cloud-init script", then paste this whole file.
#
# 1. EDIT THESE LINES before pasting (passwords: 12+ characters, no quotes inside):
ADMIN_EMAIL="you@example.com"
ADMIN_PASSWORD="CHANGE-ME-to-a-long-password"
EMPLOYEE_EMAIL=""          # optional second login to try uploading bills, e.g. demo@example.com
EMPLOYEE_PASSWORD=""       # its password (12+ characters) if you set EMPLOYEE_EMAIL
EMPLOYEE_NAME="Demo Employee"
#
# 2. After about 15-20 minutes open  https://<your-public-ip-with-dashes>.sslip.io
#    (for IP 140.238.1.2 that is https://140-238-1-2.sslip.io) and sign in with the e-mail and password above.
#    Install log on the server: /var/log/medical-claim-ai-setup.log
#
# Note: Oracle keeps this script (with the passwords) in the instance's settings. For a demo that's fine.
# For anything more, change the passwords later with scripts/create_user.py --reset-password.

exec > /var/log/medical-claim-ai-setup.log 2>&1
set -u
echo "Started $(date -u)"

if [ "$ADMIN_PASSWORD" = "CHANGE-ME-to-a-long-password" ] || [ "${#ADMIN_PASSWORD}" -lt 12 ]; then
  echo "ERROR: set ADMIN_PASSWORD (12+ characters) at the top of the initialization script"; exit 1
fi

for attempt in $(seq 1 30); do  # the network can take a moment on first boot
  if curl -fsSL https://raw.githubusercontent.com/santhosh12133/medical-claim-ai/main/deploy/setup-server.sh \
      -o /root/setup-server.sh; then
    break
  fi
  echo "Download attempt $attempt failed; retrying"; sleep 10
done
[ -s /root/setup-server.sh ] || { echo "ERROR: could not download setup-server.sh"; exit 1; }

args=(--admin-email "$ADMIN_EMAIL")
[ -z "$EMPLOYEE_EMAIL" ] || args+=(--employee-email "$EMPLOYEE_EMAIL" --employee-name "$EMPLOYEE_NAME")

MCA_ADMIN_PASSWORD="$ADMIN_PASSWORD" MCA_EMPLOYEE_PASSWORD="$EMPLOYEE_PASSWORD" bash /root/setup-server.sh "${args[@]}"
status=$?
echo "Finished $(date -u) with exit code $status"
