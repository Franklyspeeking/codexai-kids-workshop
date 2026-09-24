#!/bin/bash
# Pull a verified, off-VPS snapshot of the submission database, ZIPs and published versions.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
key_path="${CODEXAI_SSH_KEY:-$HOME/.ssh/codexai_oracle}"
test -r "$key_path" || { echo "找不到 SSH 私钥：$key_path" >&2; exit 2; }
mkdir -p "$root/backups"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
target="$root/backups/codexai-classroom-$stamp.tar.gz"
umask 077
success=0
for attempt in 1 2 3 4 5; do
  if ssh -i "$key_path" -o IdentitiesOnly=yes -o ConnectTimeout=12 ubuntu@150.230.2.138 \
    'sudo -n tar --warning=no-file-changed -czf - -C / var/lib/codexai-uploader srv/codexai-students' > "$target.partial"; then
    success=1; break
  fi
  sleep "$((attempt * 2))"
done
if [ "$success" -ne 1 ]; then
  rm -f "$target.partial"; echo '下载失败，未保留不完整备份' >&2; exit 1
fi
tar -tzf "$target.partial" > /dev/null
mv "$target.partial" "$target"
printf '备份已保存并校验：%s\n' "$target"
