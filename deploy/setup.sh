#!/bin/sh
# One-time setup on a fresh Ubuntu 24.04 Vultr VM. Run as root from /opt/reply-desk.
set -e
apt-get update -q
apt-get install -y -q python3-venv debian-keyring debian-archive-keyring apt-transport-https curl gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
apt-get update -q && apt-get install -y -q caddy

useradd --system --home /opt/reply-desk desk 2>/dev/null || true
python3 -m venv /opt/reply-desk/venv
/opt/reply-desk/venv/bin/pip install -q -r /opt/reply-desk/requirements.txt
mkdir -p /opt/reply-desk/data && chown -R desk:desk /opt/reply-desk/data

cp /opt/reply-desk/deploy/reply-desk.service /etc/systemd/system/
sed "s/__HOST__/$1/" /opt/reply-desk/deploy/Caddyfile > /etc/caddy/Caddyfile
systemctl daemon-reload
systemctl enable --now reply-desk
systemctl restart caddy
ufw allow 22 && ufw allow 80 && ufw allow 443 && ufw --force enable
