#!/usr/bin/env python3
"""Package an explicitly selected, reviewed student project into an isolated static site."""
import argparse,json,re,shutil
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('project');p.add_argument('code');p.add_argument('--output',default='prepared-students');a=p.parse_args()
if not re.fullmatch(r'[a-z][a-z0-9-]{2,30}',a.code):p.error('编号须为3-31位小写字母、数字或连字符，以字母开头')
src=Path(a.project).resolve();out=Path(a.output).resolve()/a.code
if out.exists():p.error('输出已存在，请使用新版本目录，避免覆盖')
for f in ['money/index.html','money/app.js','money/config.js','money/sw.js','money/manifest.webmanifest','style.css']:
 if not (src/f).is_file():p.error('缺少 '+f)
for f in src.rglob('*'):
 if f.is_symlink():p.error('不接受符号链接')
 if f.is_file() and (f.suffix.lower() not in {'.html','.css','.js','.json','.webmanifest','.png','.jpg','.jpeg','.svg','.webp','.md'} or f.stat().st_size>5_000_000):p.error('请检查文件类型或大小：'+str(f))
out.mkdir(parents=True)
for item in ['money','assets']:
 if (src/item).exists():shutil.copytree(src/item,out/item)
shutil.copy2(src/'style.css',out/'style.css')
f=out/'money/config.js';text=f.read_text();text,n=re.subn(r"\bid\s*:\s*(['\"]).*?\1",'id: '+json.dumps(a.code),text,count=1)
if n!=1:raise SystemExit('未找到config.js作品id，请手工检查输出后重新打包')
f.write_text(text)
m=out/'money/manifest.webmanifest';d=json.loads(m.read_text());d.update(id='./',start_url='./',scope='./');m.write_text(json.dumps(d,ensure_ascii=False))
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=money/"><a href="money/">打开我的作品</a>')
print(out);print('作品打包完成；家长链接须在教师后台审核发布后生成。');print('打包不代表安全审查通过，发布前请按验收清单检查。')
