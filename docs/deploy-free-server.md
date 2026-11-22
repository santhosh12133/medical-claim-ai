# Deploy on a free server (Oracle Cloud Always Free) or any Ubuntu VPS

This puts the whole app (website, API, background worker, PostgreSQL) on one server behind Caddy, with HTTPS.
One script does the installation; you only create the server. About 30 minutes, most of it waiting for the
first build. **No terminal is needed**: the server installs itself on first boot (step 2).

What you get:

- `https://<your-ip>.sslip.io` (free HTTPS address, no domain needed) or your own domain
- the website at `/` and the API at `/api` (Swagger UI at `/api/docs`)
- an admin account with a random password, and no demo accounts with public passwords
- the 25 synthetic demo policies loaded, so coverage questions and claim checks work right away
- daily backups of the database and uploaded files, kept for 7 days

The same script is tested in CI on a fresh Ubuntu runner, on both x86 and Arm (the kind of processor Oracle's
free machines use): install, checks through the web server, a browser test, a second run (update), and a
backup.

> Policies and test bills are synthetic. This is a demo/portfolio deployment. Don't upload real patients'
> bills: the system hasn't been evaluated on real documents, and a free VM isn't a compliant place for
> medical data.

## 1. Create the Oracle Cloud account

1. Sign up at <https://www.oracle.com/cloud/free/>. Oracle asks for a card to verify your identity; Always
   Free resources are not charged.
2. Choose your **home region** carefully: it can't be changed, and free Arm machines are only created there.
   If one region is often "out of capacity", a less busy one is easier.

## 2. Create the virtual machine

Console → **Compute → Instances → Create instance**:

| Setting | Value |
| --- | --- |
| Image | **Canonical Ubuntu 24.04** (or 22.04) |
| Shape | **Ampere → VM.Standard.A1.Flex**, **2 OCPU, 12 GB memory**. Don't go higher: Oracle's Always Free limit is 2 OCPU / 12 GB in total since August 2026, and instances above it are terminated |
| Networking | Create a new virtual cloud network with a **public subnet**; **assign a public IPv4 address** |
| SSH keys | "Generate a key pair" and **download the private key** (or paste your own public key) |
| Boot volume | Default (about 47 GB) is fine |
| **Initialization script** | Click **Show advanced options → Management → Paste cloud-init script**, and paste [`deploy/oracle-cloud-init.sh`](../deploy/oracle-cloud-init.sh) **after editing its first lines**: your e-mail and a password of 12+ characters (optionally a second, employee login) |

If you see **"Out of capacity"**, try another availability domain, try again later, or use 1 OCPU / 6 GB
(slower, but it works).

Click **Create**. When the instance is **Running**, copy its **Public IP address**, and do step 3 right
away: the server is already installing itself.

## 3. Open ports 80 and 443 in Oracle's firewall

Oracle blocks everything except SSH by default. Instance page → the subnet link → **Security** (or
**Security Lists**) → **Default Security List** → **Add Ingress Rules**, twice:

| Source CIDR | IP protocol | Destination port |
| --- | --- | --- |
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

(The server's own firewall is opened by the setup script.)

## 4. Open the app

After 15–20 minutes open `https://<public-ip-with-dashes>.sslip.io`. For IP `140.238.1.2` that is
`https://140-238-1-2.sslip.io`. Sign in on the **admin** login page with the e-mail and password from the
initialization script. That's it.

If the page doesn't load after 25 minutes, check step 3 first. The install log is at
`/var/log/medical-claim-ai-setup.log` on the server: in the Oracle console click the **Cloud Shell** icon
(`>_`, top right) and SSH in as below, or use the Instance → **Console connection** page.

### Alternative: run the script yourself over SSH

Skip the initialization script and, once the instance is running, from your computer:

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<PUBLIC_IP>
```

On the server, with your own e-mail:

```bash
curl -fsSL https://raw.githubusercontent.com/santhosh12133/medical-claim-ai/main/deploy/setup-server.sh \
  | sudo bash -s -- --admin-email you@example.com --employee-email demo@example.com
```

To read the script first: `curl -fsSLO .../deploy/setup-server.sh`, check it, then
`sudo bash setup-server.sh --admin-email you@example.com`.

The first run installs Docker, builds the images (5–15 minutes on the free machine), starts everything,
loads the demo policies and creates the accounts. It ends with the address. The passwords are printed once and
saved on the server:

```bash
sudo cat /root/medical-claim-ai-credentials.txt
```

Open the address, sign in as admin, and you're live. `--employee-email` is optional. It creates an employee
login you can use yourself or share as a demo; bills are matched to the employee's name, so set it with
`--employee-name "Full Name"` if you want uploads to pass the name check.

## Using your own domain

Create a DNS **A record** pointing your domain (e.g. `claims.example.com`) to the server's IP, wait until
`ping claims.example.com` shows that IP, then re-run the script with `--domain claims.example.com`.

## Day-to-day

All commands run on the server in `/opt/medical-claim-ai`. Shorthand used below:

```bash
cd /opt/medical-claim-ai
C="docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml"
```

| Task | Command |
| --- | --- |
| Update to the latest code | re-run the setup command (keeps data, secrets and accounts) |
| Logs | `sudo $C logs -f --tail 100` (or `... logs -f worker`) |
| Status | `sudo $C ps` |
| Add a user | `sudo $C exec api python scripts/create_user.py --email a@b.com --name "Full Name" --role employee` |
| Reset a password | `sudo $C exec api python scripts/create_user.py --email a@b.com --reset-password` |
| Restart | `sudo $C restart` |
| Stop / start | `sudo $C stop` / `sudo $C up -d` |
| Back up now | `sudo deploy/backup.sh` |

**Optional LLM features:** add `OPENAI_API_KEY=...` (or `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY=...`)
and `GPT_DECISION_ENABLED=true` / `LLM_QA_ENABLED=true` to `/opt/medical-claim-ai/.env`, then run
`sudo $C up -d`. Leave `AUTO_DECISION_ENABLED=false`.

If demo accounts were ever created on the server (`seed_demo_users.py`), delete them, because their passwords are
public:

```bash
sudo $C exec db psql -U medical_claims -d medical_claims \
  -c "DELETE FROM users WHERE email IN ('employee@demo.com','admin@demo.com') AND id NOT IN (SELECT DISTINCT user_id FROM claims WHERE user_id IS NOT NULL);"
```

## Backups and restore

`/etc/cron.d/medical-claim-ai` runs `deploy/backup.sh` every night at 02:30 (server time). Each run writes
`db-<time>.dump` (all claims, users, policies, embeddings and audits) and `files-<time>.tar.gz` (uploaded bills
and policy PDFs) to `/var/backups/medical-claim-ai/` and deletes copies older than 7 days. They're on the
same disk, so copy them elsewhere now and then (`scp`, or Oracle Object Storage, whose free tier includes
some storage).

Restore:

```bash
B=/var/backups/medical-claim-ai
sudo $C exec -T api tar -C /app -xzf - < $B/files-<time>.tar.gz
sudo $C stop api worker
sudo $C exec -T db pg_restore -U medical_claims -d medical_claims --clean --if-exists < $B/db-<time>.dump
sudo $C up -d
```

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Page doesn't load at all | Ports 80/443 not open in the Oracle security list (step 3). Check: `sudo $C logs caddy` shows certificate errors |
| "Your connection is not private" right after setup | Certificate still being issued; wait a minute. If it persists, see the row above |
| Script stops at "did not become healthy" | Usually out of memory on a small machine: check `free -h`; the script adds 4 GB of swap below 8 GB RAM |
| First claim takes a minute | The embedding model and OCR start on first use; later claims take a few seconds |
| Uploads fail on large files | Limit is 10 MB per bill (`MAX_UPLOAD_SIZE_MB` in `.env`) |
| Instance stopped by Oracle | Oracle may reclaim Always Free instances that stay idle for a long time. Upgrading the account to Pay-As-You-Go keeps Always Free resources free and avoids reclamation; set a budget alert if you do |

## Regular VPS instead of Oracle

Any Ubuntu 22.04/24.04 server with **at least 4 GB RAM** (Hetzner, DigitalOcean, Vultr, Hostinger, …) works with
the same command. Open ports 80 and 443 in the provider's firewall if it has one.

## What the script changes on the server

Installs `git`, `curl`, `openssl`, `cron` and Docker; adds a 4 GB `/swapfile` on machines with less than
8 GB RAM; opens 80/443 in `ufw`/`iptables` if they are active; puts the app in `/opt/medical-claim-ai` with a
`.env` (mode 600) holding random secrets; installs `/etc/cron.d/medical-claim-ai`; saves generated passwords to
`/root/medical-claim-ai-credentials.txt` (mode 600). Only Caddy listens on the network (80/443): the API,
website container and database ports are not published. Every option is listed by `setup-server.sh --help`.
