#!/usr/bin/env python3
"""Archive a static site without macOS extended attributes."""
import argparse
import tarfile
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('source')
p.add_argument('archive')
a = p.parse_args()
source = Path(a.source).resolve()
archive = Path(a.archive).resolve()
if not source.is_dir():
    p.error('源目录不存在')
archive.parent.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive, 'w:gz', format=tarfile.PAX_FORMAT) as output:
    for item in sorted(source.rglob('*')):
        if item.is_symlink():
            p.error('源目录不能含符号链接')
        if item.is_file() or item.is_dir():
            output.add(item, arcname=item.relative_to(source).as_posix(), recursive=False)
