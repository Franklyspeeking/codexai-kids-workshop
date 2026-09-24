#!/bin/bash
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo '用法：bash scripts/deploy-student.sh s001 /path/to/student-project' >&2
  exit 2
fi
code="$1"
project="$2"
key_path="${CODEXAI_SSH_KEY:-$HOME/.ssh/codexai_oracle}"
test -r "$key_path" || { echo "找不到 SSH 私钥：$key_path" >&2; exit 2; }
release="$(date -u +%Y%m%dT%H%M%SZ)-$$"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT

if [[ "$project" == *.zip ]]; then
  python3 "$(dirname "$0")/unpack-student-zip.py" "$project" "$scratch/unpacked"
  project="$scratch/unpacked"
fi

python3 "$(dirname "$0")/package-student.py" "$project" "$code" --output "$scratch/packages"
python3 "$(dirname "$0")/create-static-archive.py" "$scratch/packages/$code" "$scratch/$code.tar.gz"
ssh_args=(-i "$key_path" -o IdentitiesOnly=yes -o ConnectTimeout=12)
retry() {
  local n
  for n in 1 2 3 4 5; do
    if "$@"; then return 0; fi
    if [ "$n" -eq 5 ]; then return 1; fi
    sleep "$((n * 2))"
  done
}
retry scp "${ssh_args[@]}" "$scratch/$code.tar.gz" "ubuntu@150.230.2.138:/tmp/codexai-student-$code-$release.tar.gz"

remote_script="$scratch/remote-publish.sh"
cat > "$remote_script" <<'REMOTE'
set -euo pipefail
target="/srv/codexai-students/releases/$code/$release"
sudo -n install -d -m 755 "$target" /srv/codexai-students/current
if [ -f "/tmp/codexai-student-$code-$release.tar.gz" ]; then
  sudo -n tar -xzf "/tmp/codexai-student-$code-$release.tar.gz" -C "$target"
fi
sudo -n test -f "$target/money/index.html"
sudo -n test -f "$target/money/config.js"
sudo -n chown -R root:root "$target"
sudo -n find "$target" -type d -exec chmod 755 {} +
sudo -n find "$target" -type f -exec chmod 644 {} +
sudo -n ln -sfn "../releases/$code/$release" "/srv/codexai-students/current/$code.next"
sudo -n mv -Tf "/srv/codexai-students/current/$code.next" "/srv/codexai-students/current/$code"
rm -f "/tmp/codexai-student-$code-$release.tar.gz"
REMOTE
ssh_publish() { ssh "${ssh_args[@]}" ubuntu@150.230.2.138 "code='$code' release='$release' bash -s" < "$remote_script"; }
retry ssh_publish

url="https://codexai.site/works/$code/money/"
curl --noproxy '*' --resolve codexai.site:443:150.230.2.138 --fail --silent --show-error --output /dev/null "$url"
printf '作品已发布：%s\n' "$url"
if [ -x "$(dirname "$0")/.venv/bin/python" ]; then
  "$(dirname "$0")/.venv/bin/python" "$(dirname "$0")/generate-student-qr.py" "$code"
else
  echo '二维码待生成：见 scripts/generate-student-qr.py' >&2
fi
