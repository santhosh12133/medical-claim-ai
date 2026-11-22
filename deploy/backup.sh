#!/usr/bin/env bash
# Daily backup: PostgreSQL dump (claims, users, policies, embeddings, audits) + uploaded files.
# Installed as a cron job by setup-server.sh. Keeps the newest $KEEP_DAYS days in $BACKUP_DIR.
#   sudo /opt/medical-claim-ai/deploy/backup.sh
# Restore: see docs/deploy-free-server.md ("Backups and restore").
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/medical-claim-ai}"
KEEP_DAYS="${KEEP_DAYS:-7}"
COMPOSE=(docker compose -f "$APP_DIR/docker-compose.yml" -f "$APP_DIR/deploy/docker-compose.prod.yml")
STAMP="$(date +%Y%m%d-%H%M%S)"

umask 077
mkdir -p "$BACKUP_DIR"
cd "$APP_DIR"

"${COMPOSE[@]}" exec -T db pg_dump -U medical_claims -d medical_claims --format=custom > "$BACKUP_DIR/db-$STAMP.dump"
"${COMPOSE[@]}" exec -T api tar -C /app -czf - uploads policy_uploads > "$BACKUP_DIR/files-$STAMP.tar.gz"

find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name 'files-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
echo "Backup written: $BACKUP_DIR/db-$STAMP.dump, $BACKUP_DIR/files-$STAMP.tar.gz"
