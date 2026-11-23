#!/usr/bin/env bash
# Creates the whole Oracle Cloud setup for Medical Claim AI from Oracle Cloud Shell (the >_ icon in the console),
# using only Always Free resources: a network with ports 22/80/443 open, and an Ampere A1 VM (2 OCPU / 12 GB,
# falling back to 1 OCPU / 6 GB when Oracle is out of capacity) that installs the app on first boot.
#
#   curl -fsSL https://raw.githubusercontent.com/santhosh12133/medical-claim-ai/main/deploy/oracle-cloudshell-create.sh -o create.sh
#   ADMIN_EMAIL='you@example.com' ADMIN_PASSWORD='12+ characters' EMPLOYEE_PASSWORD='12+ characters' bash create.sh
#
# Safe to re-run: existing pieces (network, subnet, VM) are reused, and an existing VM's address is printed.
set -euo pipefail

NAME="medical-claim-ai"
REPO_RAW="https://raw.githubusercontent.com/santhosh12133/medical-claim-ai/main"
ADMIN_EMAIL="${ADMIN_EMAIL:?set ADMIN_EMAIL}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:?set ADMIN_PASSWORD (12+ characters)}"
EMPLOYEE_EMAIL="${EMPLOYEE_EMAIL:-employee@demo.local}"
EMPLOYEE_PASSWORD="${EMPLOYEE_PASSWORD:-}"
EMPLOYEE_NAME="${EMPLOYEE_NAME:-Employee Demo}"
WORK="$HOME/medical-claim-ai-oci"

log() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ "${#ADMIN_PASSWORD}" -ge 12 ] || die "ADMIN_PASSWORD must be at least 12 characters"
[ -z "$EMPLOYEE_PASSWORD" ] || [ "${#EMPLOYEE_PASSWORD}" -ge 12 ] || die "EMPLOYEE_PASSWORD must be at least 12 characters"
case "$ADMIN_PASSWORD$EMPLOYEE_PASSWORD" in *\"*|*\\*|*\$*|*\`*) die "Passwords can't contain \" \\ \$ or \`" ;; esac
command -v oci >/dev/null || die "Run this in Oracle Cloud Shell (the >_ icon at the top of the Oracle console)"
command -v jq >/dev/null || die "jq is missing"
mkdir -p "$WORK"

C="${OCI_TENANCY:-}"
if [ -z "$C" ]; then
  C=$(oci iam compartment list --include-root --compartment-id-in-subtree true --all \
      | jq -r '[.data[] | select(.id | startswith("ocid1.tenancy"))][0].id')
fi
[ -n "$C" ] && [ "$C" != null ] || die "Could not find your tenancy"
AD=$(oci iam availability-domain list --compartment-id "$C" | jq -r '.data[0].name')
echo "Region: ${OCI_REGION:-default}, availability domain: $AD"

# ------------------------------------------------------------------------------------------- existing VM?
EXISTING=$(oci compute instance list --compartment-id "$C" --display-name "$NAME" --all \
  | jq -r '[.data[] | select(."lifecycle-state" | test("RUNNING|PROVISIONING|STARTING"))][0].id // empty')
if [ -n "$EXISTING" ]; then
  INSTANCE="$EXISTING"
  log "The VM $NAME already exists; reusing it"
else
  # ------------------------------------------------------------------------------------------- network
  log "Network"
  VCN=$(oci network vcn list --compartment-id "$C" --display-name "$NAME-vcn" --all | jq -r '.data[0].id // empty')
  if [ -z "$VCN" ]; then
    VCN=$(oci network vcn create --compartment-id "$C" --display-name "$NAME-vcn" --cidr-blocks '["10.0.0.0/16"]' \
      --dns-label mcavcn --wait-for-state AVAILABLE 2>/dev/null | jq -r '.data.id')
    echo "Created network $NAME-vcn"
  else
    echo "Using network $NAME-vcn"
  fi
  VCN_JSON=$(oci network vcn get --vcn-id "$VCN")
  RT=$(jq -r '.data."default-route-table-id"' <<<"$VCN_JSON")
  SL=$(jq -r '.data."default-security-list-id"' <<<"$VCN_JSON")

  IGW=$(oci network internet-gateway list --compartment-id "$C" --vcn-id "$VCN" --all | jq -r '.data[0].id // empty')
  if [ -z "$IGW" ]; then
    IGW=$(oci network internet-gateway create --compartment-id "$C" --vcn-id "$VCN" --is-enabled true \
      --display-name "$NAME-igw" --wait-for-state AVAILABLE 2>/dev/null | jq -r '.data.id')
    echo "Created internet gateway"
  fi
  oci network route-table update --rt-id "$RT" --force \
    --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
  echo "Internet route set"

  cat > "$WORK/ingress.json" <<'JSON'
[
  {"source": "0.0.0.0/0", "protocol": "6", "isStateless": false, "description": "SSH",
   "tcpOptions": {"destinationPortRange": {"min": 22, "max": 22}}},
  {"source": "0.0.0.0/0", "protocol": "6", "isStateless": false, "description": "HTTP",
   "tcpOptions": {"destinationPortRange": {"min": 80, "max": 80}}},
  {"source": "0.0.0.0/0", "protocol": "6", "isStateless": false, "description": "HTTPS",
   "tcpOptions": {"destinationPortRange": {"min": 443, "max": 443}}},
  {"source": "0.0.0.0/0", "protocol": "17", "isStateless": false, "description": "HTTP/3",
   "udpOptions": {"destinationPortRange": {"min": 443, "max": 443}}},
  {"source": "0.0.0.0/0", "protocol": "1", "isStateless": false, "icmpOptions": {"type": 3, "code": 4}},
  {"source": "10.0.0.0/16", "protocol": "1", "isStateless": false, "icmpOptions": {"type": 3}}
]
JSON
  echo '[{"destination": "0.0.0.0/0", "protocol": "all", "isStateless": false}]' > "$WORK/egress.json"
  oci network security-list update --security-list-id "$SL" --force \
    --ingress-security-rules "file://$WORK/ingress.json" --egress-security-rules "file://$WORK/egress.json" >/dev/null
  echo "Opened ports 22, 80 and 443"

  SUBNET=$(oci network subnet list --compartment-id "$C" --vcn-id "$VCN" --display-name "$NAME-public" --all \
    | jq -r '.data[0].id // empty')
  if [ -z "$SUBNET" ]; then
    SUBNET=$(oci network subnet create --compartment-id "$C" --vcn-id "$VCN" --display-name "$NAME-public" \
      --cidr-block 10.0.0.0/24 --dns-label public --route-table-id "$RT" --security-list-ids "[\"$SL\"]" \
      --prohibit-public-ip-on-vnic false --wait-for-state AVAILABLE 2>/dev/null | jq -r '.data.id')
    echo "Created public subnet"
  fi

  # ------------------------------------------------------------------------------------------- VM
  log "Server image and start-up script"
  IMAGE=$(oci compute image list --compartment-id "$C" --operating-system "Canonical Ubuntu" \
      --operating-system-version "24.04" --shape VM.Standard.A1.Flex --sort-by TIMECREATED --sort-order DESC --all \
    | jq -r '[.data[] | select(."display-name" | test("Minimal") | not)][0].id // empty')
  [ -n "$IMAGE" ] || die "No Ubuntu 24.04 Arm image found in this region"
  echo "Image: $(oci compute image get --image-id "$IMAGE" | jq -r '.data."display-name"')"

  curl -fsSL "$REPO_RAW/deploy/oracle-cloud-init.sh" -o "$WORK/user-data.sh"
  sed -i \
    -e "s|^ADMIN_EMAIL=.*|ADMIN_EMAIL=\"$ADMIN_EMAIL\"|" \
    -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=\"$ADMIN_PASSWORD\"|" \
    -e "s|^EMPLOYEE_EMAIL=.*|EMPLOYEE_EMAIL=\"$([ -n "$EMPLOYEE_PASSWORD" ] && echo "$EMPLOYEE_EMAIL")\"|" \
    -e "s|^EMPLOYEE_PASSWORD=.*|EMPLOYEE_PASSWORD=\"$EMPLOYEE_PASSWORD\"|" \
    -e "s|^EMPLOYEE_NAME=.*|EMPLOYEE_NAME=\"$EMPLOYEE_NAME\"|" \
    "$WORK/user-data.sh"
  grep -q "^ADMIN_EMAIL=\"$ADMIN_EMAIL\"" "$WORK/user-data.sh" || die "Could not prepare the start-up script"

  # RSA: Oracle Cloud Shell runs in FIPS mode, which refuses ed25519 keys.
  [ -f "$HOME/.ssh/$NAME.pub" ] || ssh-keygen -q -t rsa -b 4096 -N "" -f "$HOME/.ssh/$NAME" -C "$NAME" \
    || die "Could not create an SSH key"

  log "Creating the VM (Always Free Ampere A1); this takes 1-3 minutes"
  INSTANCE=""
  for shape in '{"ocpus": 2, "memoryInGBs": 12}' '{"ocpus": 1, "memoryInGBs": 6}'; do
    echo "Trying $shape"
    if OUT=$(oci compute instance launch --compartment-id "$C" --availability-domain "$AD" --display-name "$NAME" \
        --shape VM.Standard.A1.Flex --shape-config "$shape" --image-id "$IMAGE" --subnet-id "$SUBNET" \
        --assign-public-ip true --boot-volume-size-in-gbs 50 \
        --user-data-file "$WORK/user-data.sh" --ssh-authorized-keys-file "$HOME/.ssh/$NAME.pub" \
        --wait-for-state RUNNING 2>"$WORK/launch.err"); then
      INSTANCE=$(jq -r '.data.id' <<<"$OUT")
      break
    fi
    if grep -qi "capacity" "$WORK/launch.err"; then
      echo "Oracle is out of capacity for this size right now"
    else
      cat "$WORK/launch.err" >&2
      die "The VM could not be created (details above)"
    fi
  done
  [ -n "$INSTANCE" ] || die "Oracle has no free Ampere capacity in this region at the moment. Re-run this command in an hour; it picks up where it stopped."
fi

# ------------------------------------------------------------------------------------------- result
IP=$(oci compute instance list-vnics --instance-id "$INSTANCE" | jq -r '.data[0]."public-ip" // empty')
[ -n "$IP" ] || die "The VM has no public IP yet; re-run this command in a minute"
URL="https://${IP//./-}.sslip.io"

cat <<EOF

==================================================================
 Server created: $NAME ($IP)

 The app is installing itself now. In 15-20 minutes open:

     $URL

 Admin login:   $ADMIN_EMAIL
$( [ -n "$EMPLOYEE_PASSWORD" ] && echo " Employee login: $EMPLOYEE_EMAIL" )
 (passwords: the ones you put in the command)

 Watch the installation:  ssh -i ~/.ssh/$NAME ubuntu@$IP 'tail -f /var/log/medical-claim-ai-setup.log'
==================================================================
EOF
