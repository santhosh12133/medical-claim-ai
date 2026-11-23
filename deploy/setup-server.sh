#!/usr/bin/env bash
# One-command install / update of Medical Claim AI on a single Ubuntu or Debian server
# (for example an Oracle Cloud Always Free VM). Safe to re-run: it updates the code and keeps your secrets,
# data and accounts.
#
#   curl -fsSL https://raw.githubusercontent.com/santhosh12133/medical-claim-ai/main/deploy/setup-server.sh \
#     | sudo bash -s -- --admin-email you@example.com
#
# Options:
#   --admin-email EMAIL     create an admin account with a random password (printed once, saved to
#                           /root/medical-claim-ai-credentials.txt)
#   --admin-name NAME       admin's display name (default "Administrator")
#   --employee-email EMAIL  also create an employee account to try the app or share as a demo login
#   --employee-name NAME    its display name; bills are matched to it (default "Demo Employee")
#   --domain auto|none|NAME auto (default): free HTTPS address <ip>.sslip.io; none: plain HTTP on the IP;
#                           NAME: your own domain (point its DNS A record at this server first)
#   --origin URL            the app is already behind another HTTPS proxy at URL (e.g. GitHub Codespaces):
#                           serve plain HTTP on port 80 and build the website for that address
#   --public-ip ADDR        use ADDR instead of the detected public IP (e.g. when behind NAT)
#   --auto-decisions on|off finalise clean claims automatically (on) or leave every decision to an admin (off).
#                           Flagged or low-confidence claims always go to human review. Default: keep current
#                           setting (off on a new install)
#   --no-demo-policies      do not load the 25 synthetic demo reimbursement policies
#   --app-dir DIR           install directory (default /opt/medical-claim-ai)
#   --branch NAME           git branch (default main)
#   --no-update             use the code already in --app-dir as it is (no git pull)
#   --no-firewall           do not open ports 80/443 in the host firewall
#   --no-swap               do not create a swap file on small machines
#   --no-backups            do not install the daily backup job
#
# Environment (optional): MCA_ADMIN_PASSWORD / MCA_EMPLOYEE_PASSWORD set the new accounts' passwords
# (12+ characters) instead of generating them. Used by deploy/oracle-cloud-init.sh.
# OPENAI_API_KEY or ANTHROPIC_API_KEY in the environment switches on the optional LLM features with that key.
set -euo pipefail

REPO_URL="https://github.com/santhosh12133/medical-claim-ai.git"
BRANCH="main"
APP_DIR="/opt/medical-claim-ai"
DOMAIN="auto"
ADMIN_EMAIL=""
ADMIN_NAME="Administrator"
EMPLOYEE_EMAIL=""
EMPLOYEE_NAME="Demo Employee"
DEMO_POLICIES=1
UPDATE=1
FIREWALL=1
SWAP=1
BACKUPS=1
CREDENTIALS_FILE="/root/medical-claim-ai-credentials.txt"
PUBLIC_IP_OVERRIDE=""
ORIGIN_OVERRIDE=""
AUTO_DECISIONS=""

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*" >&2; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --admin-email) ADMIN_EMAIL="${2:?}"; shift 2 ;;
    --admin-name) ADMIN_NAME="${2:?}"; shift 2 ;;
    --employee-email) EMPLOYEE_EMAIL="${2:?}"; shift 2 ;;
    --employee-name) EMPLOYEE_NAME="${2:?}"; shift 2 ;;
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --auto-decisions) AUTO_DECISIONS="${2:?}"; shift 2 ;;
    --no-demo-policies) DEMO_POLICIES=0; shift ;;
    --app-dir) APP_DIR="${2:?}"; shift 2 ;;
    --branch) BRANCH="${2:?}"; shift 2 ;;
    --repo) REPO_URL="${2:?}"; shift 2 ;;
    --no-update) UPDATE=0; shift ;;
    --no-firewall) FIREWALL=0; shift ;;
    --no-swap) SWAP=0; shift ;;
    --no-backups) BACKUPS=0; shift ;;
    --public-ip) PUBLIC_IP_OVERRIDE="${2:?}"; shift 2 ;;
    --origin) ORIGIN_OVERRIDE="${2%/}"; shift 2 ;;
    -h|--help) sed -n '2,37p' "$0"; exit 0 ;;
    *) die "Unknown option: $1 (see --help)" ;;
  esac
done

[ "$(id -u)" -eq 0 ] || die "Run as root: sudo bash setup-server.sh ..."

# ----------------------------------------------------------------------------- system
log "Checking the server"
. /etc/os-release
case "${ID:-}" in
  ubuntu|debian) ;;
  *) die "This script supports Ubuntu and Debian (found ${PRETTY_NAME:-unknown}). On Oracle Cloud choose an Ubuntu image." ;;
esac
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
CPUS=$(nproc)
echo "$PRETTY_NAME, $(uname -m), $CPUS CPU, ${MEM_MB} MB RAM"
[ "$MEM_MB" -ge 1800 ] || warn "Less than 2 GB RAM: the AI model and OCR will be slow or run out of memory."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git openssl cron >/dev/null

if [ "$SWAP" -eq 1 ] && [ "$MEM_MB" -lt 8000 ] && ! swapon --noheadings | grep -q .; then
  log "Adding a 4 GB swap file (protects against out-of-memory crashes on small machines)"
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096 status=none
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Installing Docker"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true
COMPOSE_VERSION=$(docker compose version --short 2>/dev/null | sed 's/^v//') || die "Docker Compose plugin missing"
if ! printf '2.24.4\n%s\n' "$COMPOSE_VERSION" | sort -V -C; then
  die "Docker Compose $COMPOSE_VERSION is too old (need 2.24.4+). Update Docker: curl -fsSL https://get.docker.com | sh"
fi

if [ "$FIREWALL" -eq 1 ]; then
  log "Opening ports 80 and 443 in the host firewall"
  if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; ufw allow 443/udp >/dev/null
  fi
  # Oracle Cloud Ubuntu images ship iptables rules that reject everything except SSH.
  if command -v iptables >/dev/null 2>&1 && iptables -S INPUT 2>/dev/null | grep -q -- "-j REJECT"; then
    for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
      # shellcheck disable=SC2086
      iptables -C INPUT $rule -m state --state NEW -j ACCEPT 2>/dev/null \
        || iptables -I INPUT 1 $rule -m state --state NEW -j ACCEPT
    done
    if command -v netfilter-persistent >/dev/null 2>&1; then netfilter-persistent save >/dev/null 2>&1 || true; fi
  fi
fi

# ----------------------------------------------------------------------------- code
if [ -d "$APP_DIR/.git" ]; then
  if [ "$UPDATE" -eq 1 ]; then
    log "Updating the code in $APP_DIR ($BRANCH)"
    git -C "$APP_DIR" fetch -q origin "$BRANCH"
    git -C "$APP_DIR" checkout -q "$BRANCH"
    git -C "$APP_DIR" pull -q --ff-only origin "$BRANCH"
  fi
elif [ -e "$APP_DIR/docker-compose.yml" ]; then
  log "Using the existing code in $APP_DIR"
else
  log "Downloading the code into $APP_DIR"
  git clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
COMPOSE=(docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml)

# ----------------------------------------------------------------------------- address
if [ -n "$ORIGIN_OVERRIDE" ]; then DOMAIN="origin"; fi
PUBLIC_IP="$PUBLIC_IP_OVERRIDE"
[ -n "$PUBLIC_IP" ] || [ "$DOMAIN" = "origin" ] || PUBLIC_IP=$(curl -fsS4 --max-time 6 https://api.ipify.org 2>/dev/null || curl -fsS4 --max-time 6 https://ifconfig.me 2>/dev/null || true)
case "$DOMAIN" in
  origin)
    SITE_ADDRESS=":80"; ORIGIN="$ORIGIN_OVERRIDE" ;;
  auto)
    if [[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      SITE_ADDRESS="${PUBLIC_IP//./-}.sslip.io"; ORIGIN="https://$SITE_ADDRESS"
    else
      warn "Could not detect the public IP; falling back to plain HTTP"
      SITE_ADDRESS=":80"; ORIGIN="http://localhost"
    fi ;;
  none)
    SITE_ADDRESS=":80"; ORIGIN="http://${PUBLIC_IP:-localhost}" ;;
  *)
    SITE_ADDRESS="$DOMAIN"; ORIGIN="https://$DOMAIN"
    RESOLVED=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}' || true)
    if [ -n "$PUBLIC_IP" ] && [ "$RESOLVED" != "$PUBLIC_IP" ]; then
      warn "$DOMAIN resolves to '${RESOLVED:-nothing}', not this server ($PUBLIC_IP). HTTPS will fail until its DNS A record points here."
    fi ;;
esac
echo "Public address: $ORIGIN"

# ----------------------------------------------------------------------------- configuration
set_env() {  # set_env KEY VALUE: replace or append, keeping every other line of .env
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    local tmp; tmp=$(mktemp)
    awk -v k="$key" -v v="$value" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; next} {print}' .env > "$tmp"
    cat "$tmp" > .env && rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

if [ ! -f .env ]; then
  log "Creating .env with new random secrets"
  cp .env.docker.example .env
  set_env POSTGRES_PASSWORD "$(openssl rand -hex 24)"
  set_env SECRET_KEY "$(openssl rand -hex 32)"
else
  log "Keeping the existing .env (secrets unchanged)"
fi
chmod 600 .env
set_env ENVIRONMENT production
set_env SITE_ADDRESS "$SITE_ADDRESS"
set_env CORS_ORIGINS "$ORIGIN"
set_env VITE_API_BASE_URL "$ORIGIN/api"
case "$AUTO_DECISIONS" in
  on) set_env AUTO_DECISION_ENABLED true ;;
  off) set_env AUTO_DECISION_ENABLED false ;;
  "") ;;
  *) die "--auto-decisions must be on or off" ;;
esac
if [ -n "${OPENAI_API_KEY:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  log "LLM key found in the environment: switching on GPT/Claude adjudication and Q&A"
  if [ -n "${OPENAI_API_KEY:-}" ]; then
    set_env LLM_PROVIDER openai; set_env OPENAI_API_KEY "$OPENAI_API_KEY"
  else
    set_env LLM_PROVIDER anthropic; set_env ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY"
  fi
  set_env GPT_DECISION_ENABLED true
  set_env LLM_QA_ENABLED true
fi
WORKERS=$(( CPUS < 4 ? CPUS : 4 ))
grep -q '^CLAIM_WORKER_CONCURRENCY=' .env || set_env CLAIM_WORKER_CONCURRENCY "$WORKERS"
if grep -q '^AUTO_DECISION_ENABLED=true' .env; then
  echo "Automatic decisions: ON (clean claims are finalised; flagged or uncertain ones go to an admin)"
else
  echo "Automatic decisions: OFF (every claim waits for an admin)"
fi

# ----------------------------------------------------------------------------- start
log "Building and starting the app (the first build takes 5-15 minutes)"
"${COMPOSE[@]}" up -d --build --remove-orphans --wait --wait-timeout 900 \
  || {
    "${COMPOSE[@]}" logs --tail 60
    echo; echo "Service status (the one that is not running/healthy is the problem):"
    "${COMPOSE[@]}" ps -a --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
    die "The app did not become healthy. Re-run the same command once (a slow first start can time out); if it fails again, send the status table above."
  }
# The website is built for one public address. Compose can keep the old container running after a rebuild
# (seen on arm64), so always recreate it: it's stateless nginx and restarts in about a second.
"${COMPOSE[@]}" up -d --no-deps --force-recreate --wait --wait-timeout 120 frontend
"${COMPOSE[@]}" ps

api_python() { "${COMPOSE[@]}" exec -T "$@"; }

if [ "$DEMO_POLICIES" -eq 1 ]; then
  log "Loading the synthetic demo policies (downloads the ~90 MB embedding model once)"
  api_python api python -m scripts.seed_demo_policies
fi

DEMO_LEFT=$(api_python api python -c "
import models
from database import SessionLocal
from models_user import User
with SessionLocal() as db:
    print(db.query(User).filter(User.email.in_(['employee@demo.com', 'admin@demo.com'])).count())" | tail -1)
[ "${DEMO_LEFT:-0}" = "0" ] || warn "Demo accounts with public passwords exist on this server; delete them (see docs/deploy-free-server.md)."

create_account() {  # create_account EMAIL NAME ROLE [PASSWORD]
  local output env_args=()
  [ -z "${4:-}" ] || env_args=(-e "MCA_PASSWORD=$4")
  if output=$(api_python "${env_args[@]}" api python scripts/create_user.py --email "$1" --name "$2" --role "$3" 2>&1); then
    echo "$output"
    local password; password=$(printf '%s\n' "$output" | sed -n 's/^Generated password.*: //p')
    if [ -n "$password" ]; then
      umask 077
      printf '%s  %s  %s  password: %s\n' "$(date -u +%FT%TZ)" "$3" "$1" "$password" >> "$CREDENTIALS_FILE"
    fi
  elif printf '%s' "$output" | grep -q "already exists"; then
    echo "$1 already exists; password unchanged"
  else
    printf '%s\n' "$output"; die "Could not create the account $1"
  fi
}
if [ -n "$ADMIN_EMAIL" ]; then
  log "Admin account"; create_account "$ADMIN_EMAIL" "$ADMIN_NAME" admin "${MCA_ADMIN_PASSWORD:-}"
fi
if [ -n "$EMPLOYEE_EMAIL" ]; then
  log "Employee account"; create_account "$EMPLOYEE_EMAIL" "$EMPLOYEE_NAME" employee "${MCA_EMPLOYEE_PASSWORD:-}"
fi

if [ "$BACKUPS" -eq 1 ]; then
  log "Installing the daily backup job (02:30, keeps 7 days in /var/backups/medical-claim-ai)"
  printf 'SHELL=/bin/bash\n30 2 * * * root APP_DIR=%s %s/deploy/backup.sh >> /var/log/medical-claim-ai-backup.log 2>&1\n' \
    "$APP_DIR" "$APP_DIR" > /etc/cron.d/medical-claim-ai
  chmod 644 /etc/cron.d/medical-claim-ai
fi

# ----------------------------------------------------------------------------- verify
log "Checking the public address through the web server"
if [ "$SITE_ADDRESS" = ":80" ]; then
  CHECK=(curl -fsS --max-time 10 http://127.0.0.1/api/health/ready)
else
  CHECK=(curl -fsS --max-time 10 --resolve "$SITE_ADDRESS:443:127.0.0.1" "https://$SITE_ADDRESS/api/health/ready")
fi
OK=0
for _ in $(seq 1 30); do
  if "${CHECK[@]}" >/dev/null 2>&1; then OK=1; break; fi
  sleep 4
done
if [ "$OK" -eq 1 ]; then
  echo "API reachable through the web server"
else
  warn "The web server did not answer yet. For HTTPS this usually means ports 80/443 are closed in the cloud
  firewall (Oracle: VCN security list ingress rules), so the certificate could not be issued.
  Check: ${COMPOSE[*]} logs caddy"
fi

cat <<EOF

------------------------------------------------------------------
 Medical Claim AI is running.

 Open:        $ORIGIN
 API docs:    $ORIGIN/api/docs
 Accounts:    $( [ -f "$CREDENTIALS_FILE" ] && echo "sudo cat $CREDENTIALS_FILE" || echo "create one: cd $APP_DIR && sudo ${COMPOSE[*]} exec api python scripts/create_user.py --email you@example.com --name 'You' --role admin" )
 Update:      re-run this script (keeps data, secrets and accounts)
 Logs:        cd $APP_DIR && sudo ${COMPOSE[*]} logs -f
 Backups:     $( [ "$BACKUPS" -eq 1 ] && echo "daily to /var/backups/medical-claim-ai" || echo "not installed" )

 Policies and test bills are synthetic. Do not upload real medical bills until the
 system has been evaluated on real (anonymised) documents.
------------------------------------------------------------------
EOF
