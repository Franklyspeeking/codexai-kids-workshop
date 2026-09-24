#!/bin/bash
cd "$(dirname "$0")" || exit 1
bash scripts/backup-vps-classroom.sh
status=$?
printf '\n按回车关闭窗口…'
read -r _
exit "$status"
