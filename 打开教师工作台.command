#!/bin/bash
cd "$(dirname "$0")" || exit 1
secret="preparation/.teacher-admin-token"
if [ ! -r "$secret" ]; then
  echo '找不到教师密钥，请先检查本机准备文件夹。'
  read -r _
  exit 1
fi
tr -d '\n' < "$secret" | pbcopy
open 'https://www.codexai.site/teacher/'
echo '教师工作台已打开，密钥已复制。请在页面的密钥框中粘贴。'
printf '按回车关闭窗口…'
read -r _
