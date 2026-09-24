#!/usr/bin/env python3
"""Build the one universal, student-safe starter ZIP served by the workshop site."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
source = root / 'preparation/templates/starter'
output = root / 'codexai-site/dist/classroom/零花钱计划师-起始包.zip'
folder = '零花钱计划师-起始项目'
instructions = '''# 从这里开始

1. 解压整个文件包，不要直接在压缩包里编辑。
2. 把“零花钱计划师-起始项目”整个文件夹在 TRAE 国内版中打开。
3. 按老师发的学生任务卡，先改工具名称、愿望和目标，再完成自己的规则。
4. 每次请 AI 只改一件事，预览后自己操作并记录测试结果。
5. 做好后把整个项目文件夹压缩为“老师分配的作品编号.zip”，交回老师。不要只交 HTML 文件。
6. 不写真实姓名、学校、家庭账目、密码或 API 密钥。服务器由老师发布，学生不需要服务器账号。

项目文件都在这个文件夹：money/index.html 是工具页面，money/config.js 是默认设置，style.css 是样式。
在电脑上预览时，请通过本地 HTTP 预览，不要把双击打开的 file:// 页面当作最后结果。
'''
output.parent.mkdir(parents=True, exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
    archive.writestr(f'{folder}/开始这里.md', instructions)
    for item in sorted(source.rglob('*')):
        if item.is_symlink():
            raise SystemExit(f'模板里有符号链接：{item}')
        if item.is_file():
            archive.write(item, f'{folder}/{item.relative_to(source).as_posix()}')
print(output)
