#!/bin/bash
# Manual fallback for teacher-reviewed projects. Uses the same private-link workflow as the classroom UI.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo '用法：bash scripts/deploy-student.sh 学生编号 项目ZIP或文件夹' >&2
  exit 2
fi
python3 "$(dirname "$0")/deploy-student.py" "$1" "$2"
