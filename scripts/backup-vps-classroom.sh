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
    'bash -s' > "$target.partial" <<'REMOTE'; then
set -euo pipefail
scratch="$(mktemp -d)"
trap 'sudo -n rm -rf -- "$scratch"' EXIT
sudo -n python3 - "$scratch/db-snapshot.sqlite3" <<'PY'
import sqlite3,sys
source=sqlite3.connect('file:/var/lib/codexai-uploader/classroom.sqlite3?mode=ro',uri=True)
target=sqlite3.connect(sys.argv[1])
source.backup(target)
target.close();source.close()
PY
sudo -n tar --warning=no-file-changed --exclude=var/lib/codexai-uploader/classroom.sqlite3 \
  --transform='s|^db-snapshot.sqlite3$|var/lib/codexai-uploader/classroom.sqlite3|' \
  -czf - -C / var/lib/codexai-uploader srv/codexai-students \
  -C "$scratch" db-snapshot.sqlite3
REMOTE
    success=1; break
  fi
  sleep "$((attempt * 2))"
done
if [ "$success" -ne 1 ]; then
  rm -f "$target.partial"; echo '下载失败，未保留不完整备份' >&2; exit 1
fi
tar -tzf "$target.partial" > /dev/null
db_count="$(tar -tzf "$target.partial" | awk '$0=="var/lib/codexai-uploader/classroom.sqlite3" {count++} END {print count+0}')"
if [ "$db_count" -ne 1 ]; then
  rm -f "$target.partial"; echo '备份未包含唯一的数据库快照' >&2; exit 1
fi
if ! python3 - "$target.partial" <<'PY'
import sqlite3,sys,tarfile,tempfile
with tarfile.open(sys.argv[1],'r:gz') as archive:
    source=archive.extractfile('var/lib/codexai-uploader/classroom.sqlite3')
    if source is None:raise SystemExit(1)
    with tempfile.NamedTemporaryFile() as restored:
        while data:=source.read(1024*1024):restored.write(data)
        restored.flush()
        with sqlite3.connect(f'file:{restored.name}?mode=ro',uri=True) as conn:
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise SystemExit(1)
PY
then
  rm -f "$target.partial"; echo '数据库快照完整性检查失败' >&2; exit 1
fi
mv "$target.partial" "$target"
printf '备份已保存并校验：%s\n' "$target"
