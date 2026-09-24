# 儿童 AI 创作工作坊｜首课准备

正式网站：[codexai.site](https://codexai.site/) · 教师演示作品：[零花钱计划师](https://codexai.site/money/) · [学生下载入口](https://codexai.site/classroom/)

本文件夹是老师的本地工作区。`codexai-site/dist` 是已部署的公开网站；`preparation` 是课堂资料；`scripts` 是发布工具。不要把整个工作区上传到公网。九张 PNG 为用户提供的原始海报，网站使用压缩后的 JPG。

## 先看这些

- [210 分钟课程执行脚本](preparation/01-课程执行脚本.md)：包含讲解台词、检查点、快慢班调整和故障处理。
- [学生任务与 Prompt 卡](preparation/02-学生任务与Prompt卡.md)：可打印发给孩子。
- [渠道演示与家长使用卡](preparation/03-渠道演示与家长使用卡.md)：演示顺序和家长手机操作。
- [发布与长期维护手册](preparation/04-发布与维护手册.md)：收作业、审核、上线、回滚、备份。
- [学生模板说明](preparation/templates/README.md)：`starter` 是课堂起点，`standard` 是救援版本。
- [网站二维码](preparation/二维码/课程网站.png) / [示范工具二维码](preparation/二维码/零花钱计划师.png)。

## 全班交付流程

1. 孩子在笔记本打开 `https://codexai.site/classroom/`，下载统一的ZIP起始包，解压整个文件夹，在TRAE国内版中修改。老师给每人独立编号，如 `s001`；下一班换新编号。
2. 孩子把整个项目文件夹压缩成 `s001.zip` 交回老师。老师先预览、测试并检查文件，把通过的ZIP或同名文件夹放进 `preparation/待发布-已审核/`。
3. 在此项目根目录运行 `bash scripts/publish-approved.sh`。脚本逐个上传，生成 `preparation/交付清单/日期时间.csv` 和每人一张二维码。单个补发可运行 `bash scripts/deploy-student.sh s001 /收件位置/s001.zip`。
4. 家长扫描二维码或复制交付清单里的完整链接，在手机系统浏览器打开 `https://codexai.site/works/s001/money/`，等离线准备完成，添加桌面，并从桌面入口重开、记一笔、飞行模式复测。

发布脚本默认使用本机 `~/.ssh/codexai_oracle`。它只上传经老师选定的静态文件，保留服务器历史版本。每个编号沿用同一地址；手机账本留在该手机浏览器中，不会同步到服务器。首次联网后页面会准备离线缓存，但浏览器清理数据或换手机仍可能丢失账本，家长要定期导出备份。二维码生成功能使用 `scripts/.venv` 中的 Python 依赖，换电脑时按 `scripts/qr-requirements.txt` 安装。

## 尚需老师现场完成

PPT、班级人数与助教安排由老师负责。正式儿童试班之前，还应在实际上课的电脑与账号上验证 TRAE 国内版的登录、可用额度、年龄适用要求和多人同网生成速度；在家长的实际手机上完成一次“扫码、添加桌面、关闭重开”的验收。当前完成的是教师演示网站和可复用发布流程，不能把电脑浏览器测试当作家长手机实测。
