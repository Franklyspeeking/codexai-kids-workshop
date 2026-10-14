#!/bin/bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
key_path="${CODEXAI_SSH_KEY:-$HOME/.ssh/codexai_oracle}"
token_file="$root/preparation/.teacher-admin-token"
test -r "$key_path" || { echo "找不到 SSH 私钥：$key_path" >&2; exit 2; }
if python3 -c 'import sys' >/dev/null 2>&1; then python_cmd=python3
elif python -c 'import sys' >/dev/null 2>&1; then python_cmd=python
else echo '找不到可用的 Python 3' >&2; exit 2
fi
if [ ! -f "$token_file" ]; then
  umask 077
  "$python_cmd" -c 'import secrets,sys; open(sys.argv[1],"w").write(secrets.token_hex(32)+"\n")' "$token_file"
fi
release="$(date -u +%Y%m%dT%H%M%SZ)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
cp "$root/scripts/upload-service.py" "$root/scripts/story_director_ai.py" "$root/scripts/unpack-student-zip.py" "$root/scripts/package-student.py" "$root/scripts/prepare-web-zip.py" "$scratch/"
tar -czf "$scratch/service.tar.gz" -C "$scratch" upload-service.py story_director_ai.py unpack-student-zip.py package-student.py prepare-web-zip.py
ssh_args=(-i "$key_path" -o IdentitiesOnly=yes -o ConnectTimeout=12)
retry() {
  local n
  for n in 1 2 3 4 5; do
    if "$@"; then return 0; fi
    if [ "$n" -eq 5 ]; then return 1; fi
    sleep "$((n * 2))"
  done
}
retry scp "${ssh_args[@]}" "$scratch/service.tar.gz" ubuntu@150.230.2.138:/tmp/codexai-uploader-service.tar.gz
retry scp "${ssh_args[@]}" "$root/scripts/codexai-uploader.service" ubuntu@150.230.2.138:/tmp/codexai-uploader.service
retry scp "${ssh_args[@]}" "$token_file" ubuntu@150.230.2.138:/tmp/codexai-uploader-token
cat > "$scratch/remote-install.sh" <<'REMOTE'
set -euo pipefail
if ! getent group codexai >/dev/null; then sudo -n groupadd --system codexai; fi
if ! id codexai >/dev/null 2>&1; then sudo -n useradd --system --gid codexai --no-create-home --shell /usr/sbin/nologin codexai; fi
sudo -n apt-get install -y -qq python3-qrcode python3-pil >/dev/null
sudo -n install -d -m 755 /opt/codexai-uploader/releases/"$release" /opt/codexai-uploader
sudo -n tar -xzf /tmp/codexai-uploader-service.tar.gz -C /opt/codexai-uploader/releases/"$release"
sudo -n chown -R root:root /opt/codexai-uploader/releases/"$release"
sudo -n install -d -o codexai -g codexai -m 700 /var/lib/codexai-uploader
sudo -n chown -R codexai:codexai /srv/codexai-students
if sudo -n test -s /etc/codexai-uploader.env; then
  printf 'Preserved existing uploader environment\n'
else
  sudo -n sh -c 'printf "CODEXAI_ADMIN_TOKEN=%s\n" "$(cat /tmp/codexai-uploader-token)" > /etc/codexai-uploader.env'
fi
sudo -n chmod 600 /etc/codexai-uploader.env
sudo -n rm -f /tmp/codexai-uploader-token
sudo -n install -m 644 /tmp/codexai-uploader.service /etc/systemd/system/codexai-uploader.service
sudo -n ln -sfn releases/"$release" /opt/codexai-uploader/next
sudo -n mv -Tf /opt/codexai-uploader/next /opt/codexai-uploader/current
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now codexai-uploader
sudo -n systemctl restart codexai-uploader
systemctl is-active codexai-uploader
healthy=0
for check in 1 2 3 4 5 6 7 8 9 10; do
  if curl --fail --silent --show-error http://127.0.0.1:8766/api/health; then healthy=1; break; fi
  sleep 1
done
test "$healthy" -eq 1
REMOTE
retry ssh "${ssh_args[@]}" ubuntu@150.230.2.138 "release='$release' bash -s" < "$scratch/remote-install.sh"
printf '\n教师密钥保存在：%s\n' "$token_file"
