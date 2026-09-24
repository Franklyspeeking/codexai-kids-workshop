#!/bin/bash
# macOS Finder: double-click after reviewed projects are placed in preparation/待发布-已审核.
cd "$(dirname "$0")" || exit 1
bash scripts/publish-approved.sh
result=$?
printf '\n发布流程结束。按回车键关闭窗口。\n'
read -r _
exit "$result"
