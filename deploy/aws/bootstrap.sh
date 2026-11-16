#!/usr/bin/env bash
# Runs ON the EC2 instance, as root, through SSM Run Command (deploy/aws.sh sends it).
# Installs what the stack needs, installs the release, writes .env from Parameter Store and
# the Caddy (HTTPS) configuration, then runs the project's own ./start.sh. Safe to rerun.
#
# Usage: bootstrap.sh <release-dir> <domain> <jupyter-domain> <jupyter-cidrs> <ssm-path> <region>
#   jupyter-cidrs: comma-separated, e.g. "203.0.113.0/24,198.51.100.7/32"
set -euo pipefail

release="$1" domain="$2" jupyter_domain="$3" jupyter_cidrs="$4" ssm_path="$5" region="$6"
app=/opt/glassbox
user=ubuntu
export PATH="$PATH:/snap/bin" DEBIAN_FRONTEND=noninteractive HOME="${HOME:-/root}"

exec > >(tee -a /var/log/glassbox-deploy.log) 2>&1
echo "=== $(date -u +%FT%TZ) deploying $(basename "$release") to https://${domain}"

# --- 1. Packages: Docker with the Compose plugin, Caddy (HTTPS), rsync ---------------------
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1 \
  || ! command -v caddy >/dev/null || ! command -v rsync >/dev/null; then
  echo "Installing Docker, Compose, Caddy..."
  apt-get update -q
  apt-get install -y -q docker.io docker-compose-v2 docker-buildx caddy rsync
fi
systemctl enable --now docker caddy
usermod -aG docker "$user"

# --- 2. The release: replace the code, keep generated and local state ----------------------
mkdir -p "$app"
rsync -a --delete \
  --exclude /.env \
  --exclude '/data/*.csv' \
  --exclude /librechat/librechat.yaml \
  --exclude /tests/reports/ \
  "$release"/ "$app"/
chown -R "$user:$user" "$app"

# --- 3. .env from Parameter Store (/glassbox/<stack>/<KEY>) --------------------------------
umask 077
{
  echo "# Written by deploy/aws/bootstrap.sh from SSM Parameter Store ${ssm_path}; edit there."
  aws ssm get-parameters-by-path --region "$region" --path "$ssm_path" --recursive \
    --with-decryption --query 'Parameters[].[Name,Value]' --output text |
    while IFS=$'\t' read -r name value; do printf '%s=%s\n' "${name##*/}" "$value"; done
  echo "LIBRECHAT_PUBLIC_URL=https://${domain}"
} >"$app/.env.new"
grep -q '^OPENAI_API_KEY=.' "$app/.env.new" || { echo "No secrets found under ${ssm_path}" >&2; exit 1; }
mv "$app/.env.new" "$app/.env"
chown "$user:$user" "$app/.env"
umask 022

# --- 4. Caddy: HTTPS for both sites, certificates from Let's Encrypt -----------------------
cat >/etc/caddy/Caddyfile.new <<EOF
# Written by deploy/aws/bootstrap.sh; rerun ./deploy/aws.sh up to change it.
${domain} {
	reverse_proxy 127.0.0.1:3080
}

# JupyterLab runs code: only the allow-listed networks get past this point, then its token.
${jupyter_domain} {
	@denied not remote_ip ${jupyter_cidrs//,/ }
	respond @denied "Forbidden" 403
	reverse_proxy 127.0.0.1:8888
}
EOF
caddy validate --config /etc/caddy/Caddyfile.new --adapter caddyfile >/dev/null
mv /etc/caddy/Caddyfile.new /etc/caddy/Caddyfile
systemctl reload caddy

# --- 5. The stack: the same start.sh as on a laptop ----------------------------------------
# sudo starts a fresh login, so the docker group just added applies. Images are pulled quietly
# first: download progress bars would fill SSM's 24 KB output limit and hide the useful lines.
# The admin password is filtered out so it doesn't end up in the SSM command history.
sudo -u "$user" -H bash -c "cd '$app' && docker compose pull --quiet --ignore-buildable && docker pull -q python:3.12-slim >/dev/null"
sudo -u "$user" -H bash -c "cd '$app' && ./start.sh" | sed -u '/password:/d'

# The two backends answer locally before Caddy is asked to serve them
curl -fsS --max-time 10 http://127.0.0.1:3080/health >/dev/null
curl -fsS --max-time 10 -o /dev/null http://127.0.0.1:8888/api
echo "=== $(date -u +%FT%TZ) deployed"
