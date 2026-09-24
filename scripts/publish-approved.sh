#!/bin/bash
# Batch-publish only projects the teacher has reviewed and placed in the approved inbox.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
inbox="${1:-$root/preparation/待发布-已审核}"
test -d "$inbox" || { echo "找不到已审核收件箱：$inbox" >&2; exit 2; }
shopt -s nullglob
items=("$inbox"/*)
if [ "${#items[@]}" -eq 0 ]; then
  echo "已审核收件箱为空：$inbox"
  exit 0
fi

report_dir="$root/preparation/交付清单"
mkdir -p "$report_dir"
report="$report_dir/$(date +%Y%m%d-%H%M%S).csv"
printf '\357\273\277作品编号,作品链接,二维码文件,发布结果\n' > "$report"
success=0
failed=0
for item in "${items[@]}"; do
  name="$(basename "$item")"
  if [[ "$name" == *.zip ]]; then code="${name%.zip}"; else code="$name"; fi
  if [[ ! "$code" =~ ^[a-z][a-z0-9-]{2,30}$ ]] || { [ ! -d "$item" ] && [[ "$item" != *.zip ]]; }; then
    echo "跳过：文件名必须是作品编号.zip，或作品编号文件夹：$name" >&2
    ((failed+=1))
    continue
  fi
  echo "正在发布：$code"
  if bash "$root/scripts/deploy-student.sh" "$code" "$item"; then
    url="https://codexai.site/works/$code/money/"
    qr="$root/preparation/二维码/学生作品/$code.png"
    printf '%s,%s,%s,成功\n' "$code" "$url" "$qr" >> "$report"
    ((success+=1))
  else
    printf '%s,,,失败-请检查终端输出\n' "$code" >> "$report"
    ((failed+=1))
  fi
done
printf '已发布 %s 个，失败或跳过 %s 个。交付清单：%s\n' "$success" "$failed" "$report"
if [ "$failed" -ne 0 ]; then exit 1; fi
