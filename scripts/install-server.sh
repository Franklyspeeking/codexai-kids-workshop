#!/bin/bash
set -euo pipefail
sudo -n apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key -o /tmp/codexai-caddy.gpg
sudo -n gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg /tmp/codexai-caddy.gpg
curl -1fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /tmp/codexai-caddy.list
sudo -n install -m 644 /tmp/codexai-caddy.list /etc/apt/sources.list.d/caddy-stable.list
sudo -n apt-get update -qq
sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y caddy
sudo -n mkdir -p /srv/codexai/releases /var/log/caddy
sudo -n chown caddy:caddy /var/log/caddy
