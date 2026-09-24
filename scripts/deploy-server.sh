#!/bin/bash
set -euo pipefail
release="$(date -u +%Y%m%dT%H%M%SZ)"
source_dir="$(cd "$(dirname "$0")/../codexai-site/dist" && pwd)"
key_path="${CODEXAI_SSH_KEY:-$HOME/.ssh/codexai_oracle}"
test -r "$key_path" || { echo "找不到 SSH 私钥：$key_path" >&2; exit 2; }
ssh_args=(-i "$key_path" -o IdentitiesOnly=yes -o ConnectTimeout=12)
retry() {
  local n
  for n in 1 2 3 4 5; do
    if "$@"; then return 0; fi
    if [ "$n" -eq 5 ]; then return 1; fi
    sleep "$((n * 2))"
  done
}
archive="/tmp/codexai-${release}.tar.gz"
python3 "$(dirname "$0")/create-static-archive.py" "$source_dir" "$archive"
retry scp "${ssh_args[@]}" "$archive" ubuntu@150.230.2.138:"/tmp/codexai-${release}.tar.gz"
retry scp "${ssh_args[@]}" "$(dirname "$0")/Caddyfile" ubuntu@150.230.2.138:/tmp/codexai-Caddyfile
remote_script="$(mktemp)"
trap 'python3 -c '\''from pathlib import Path; import sys; Path(sys.argv[1]).unlink(missing_ok=True)'\'' "$remote_script"' EXIT
cat > "$remote_script" <<'REMOTE'
set -euo pipefail
sudo -n install -d -m 755 /srv/codexai/releases/"$release"
sudo -n tar -xzf /tmp/codexai-"$release".tar.gz -C /srv/codexai/releases/"$release"
sudo -n chown -R root:root /srv/codexai/releases/"$release"
sudo -n find /srv/codexai/releases/"$release" -type d -exec chmod 755 {} +
sudo -n find /srv/codexai/releases/"$release" -type f -exec chmod 644 {} +
sudo -n install -d -m 755 /srv/codexai-students/current /srv/codexai-students/releases
sudo -n install -d -o codexai -g codexai -m 755 /srv/codexai-students/v2/current /srv/codexai-students/v2/releases
sudo -n chmod 755 /srv/codexai-students/v2
sudo -n ln -sfn /srv/codexai-students/current /srv/codexai/releases/"$release"/works
sudo -n ln -sfn /srv/codexai-students/v2/current /srv/codexai/releases/"$release"/projects
sudo -n caddy validate --config /tmp/codexai-Caddyfile --adapter caddyfile
sudo -n install -m 644 /tmp/codexai-Caddyfile /etc/caddy/Caddyfile
sudo -n ln -sfn /srv/codexai/releases/"$release" /srv/codexai/next
sudo -n mv -Tf /srv/codexai/next /srv/codexai/current
sudo -n systemctl enable --now caddy
sudo -n systemctl reload caddy
systemctl is-active caddy
printf 'Published release %s\n' "$release"
REMOTE
ssh_publish() { ssh "${ssh_args[@]}" ubuntu@150.230.2.138 "release='$release' bash -s" < "$remote_script"; }
retry ssh_publish
