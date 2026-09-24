#!/usr/bin/env python3
"""Safely unpack one reviewed student ZIP into a clean project folder."""
import argparse
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

p = argparse.ArgumentParser()
p.add_argument('archive')
p.add_argument('destination')
a = p.parse_args()
archive = Path(a.archive)
destination = Path(a.destination)
allowed = {'.html', '.css', '.js', '.json', '.webmanifest', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.md', '.txt'}
required = {'money/index.html', 'money/app.js', 'money/config.js', 'money/sw.js', 'money/manifest.webmanifest', 'style.css'}
if not archive.is_file() or archive.stat().st_size > 25_000_000:
    p.error('压缩包不存在或超过25MB')

with ZipFile(archive) as z:
    items = [i for i in z.infolist() if not i.is_dir() and not i.filename.startswith('__MACOSX/') and not i.filename.endswith('/.DS_Store') and not i.filename.endswith('/Thumbs.db')]
    if len(items) > 200:
        p.error('文件过多，请只交项目文件夹')
    roots = set()
    for item in items:
        name = item.filename
        path = PurePosixPath(name)
        if name.startswith('/') or '\\' in name or '..' in path.parts or any(part.startswith('.') for part in path.parts):
            p.error(f'不安全的路径：{name}')
        if stat.S_ISLNK(item.external_attr >> 16):
            p.error(f'不接受符号链接：{name}')
        if item.file_size > 5_000_000 or path.suffix.lower() not in allowed:
            p.error(f'请检查文件类型或大小：{name}')
        if name.endswith('money/index.html'):
            roots.add(name[:-len('money/index.html')])
    if len(roots) != 1:
        p.error('找不到唯一的项目根目录；请压缩整个项目文件夹')
    prefix = roots.pop()
    selected = [i for i in items if i.filename.startswith(prefix)]
    paths = [i.filename[len(prefix):] for i in selected]
    if not required.issubset(paths) or len(paths) != len(set(paths)):
        p.error('项目文件缺失或重名')
    if sum(i.file_size for i in selected) > 25_000_000:
        p.error('项目解压后超过25MB')
    destination.mkdir(parents=True, exist_ok=False)
    for item, relative in zip(selected, paths):
        if not relative or PurePosixPath(relative).suffix.lower() not in allowed:
            p.error('项目包含不允许的文件')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(item) as src, target.open('wb') as dst:
            while block := src.read(1024 * 1024):
                dst.write(block)
print(destination.resolve())
