#!/usr/bin/env python3
"""Validate a child's static web ZIP and add an offline shell for its own URL."""
import argparse
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

ALLOWED = {'.html', '.css', '.js', '.json', '.webmanifest', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.ico', '.md', '.txt'}
RESERVED = {'codexai-sw.js', 'codexai-register.js', 'codexai-manifest.webmanifest'}
MAX_BYTES = 25_000_000


def prepare(archive: Path, destination: Path, title: str):
    if not archive.is_file() or archive.stat().st_size > MAX_BYTES:
        raise ValueError('ZIP 文件不存在或超过 25MB')
    if destination.exists():
        raise ValueError('输出目录已存在')
    try:
        with ZipFile(archive) as zipped:
            files = [item for item in zipped.infolist() if not item.is_dir()
                     and not item.filename.startswith('__MACOSX/')
                     and not item.filename.endswith(('/.DS_Store', '/Thumbs.db'))]
            if not files or len(files) > 200:
                raise ValueError('ZIP 文件数量须为 1–200 个')
            roots = [name for name in (item.filename for item in files)
                     if name == 'index.html' or (name.endswith('/index.html') and name.count('/') == 1)]
            if len(roots) != 1:
                raise ValueError('ZIP 中须有唯一的首页 index.html，位于根目录或一层项目文件夹内')
            prefix = roots[0][:-len('index.html')]
            selected = []
            total = 0
            for item in files:
                name = item.filename
                if name.startswith('/') or '\\' in name or '..' in PurePosixPath(name).parts:
                    raise ValueError('ZIP 内含不安全的文件路径')
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise ValueError('ZIP 不接受符号链接')
                if not name.startswith(prefix):
                    raise ValueError('ZIP 只能包含同一个项目文件夹')
                relative = name[len(prefix):]
                path = PurePosixPath(relative)
                if not relative or any(part.startswith('.') for part in path.parts) or path.suffix.lower() not in ALLOWED:
                    raise ValueError('文件类型或路径不允许：' + relative[:80])
                if path.parts[0] in RESERVED:
                    raise ValueError('请不要创建 codexai- 开头的系统文件')
                if item.file_size > 5_000_000:
                    raise ValueError('单个文件不能超过 5MB')
                total += item.file_size
                selected.append((item, relative))
            if total > MAX_BYTES or len({name for _, name in selected}) != len(selected):
                raise ValueError('解压后文件过大或文件名重复')
            destination.mkdir(parents=True)
            for item, relative in selected:
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(item) as source, target.open('wb') as output:
                    while block := source.read(1024 * 1024):
                        output.write(block)
    except BadZipFile as exc:
        raise ValueError('ZIP 文件损坏，请重新压缩') from exc

    index = destination/'index.html'
    html = index.read_text(encoding='utf-8')
    if not re.search(r'<html\b', html, re.I):
        raise ValueError('首页不是有效的 HTML 文件')
    files = sorted(path.relative_to(destination).as_posix() for path in destination.rglob('*') if path.is_file())
    version = hashlib.sha256(('\n'.join(files) + html).encode()).hexdigest()[:12]
    cache = 'codexai-web-' + version + ':'
    assets = ['./'] + ['./' + name for name in files + sorted(RESERVED)]
    sw = f'''const CACHE={json.dumps(cache)}+self.registration.scope;
const ASSETS={json.dumps(assets,ensure_ascii=False)};
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('codexai-web-')&&k.endsWith(self.registration.scope)&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{{if(e.request.method!=='GET'||!e.request.url.startsWith(self.registration.scope))return;e.respondWith(fetch(e.request).then(r=>{{if(r.ok)e.waitUntil(caches.open(CACHE).then(c=>c.put(e.request,r.clone())));return r;}}).catch(()=>caches.match(e.request,{{ignoreSearch:true}})));}});
'''
    (destination/'codexai-sw.js').write_text(sw, encoding='utf-8')
    (destination/'codexai-register.js').write_text("if('serviceWorker' in navigator&&window.isSecureContext)navigator.serviceWorker.register('./codexai-sw.js',{scope:'./'}).catch(()=>{});\n", encoding='utf-8')
    manifest = {'name': title[:48], 'short_name': title[:14], 'id': './', 'start_url': './', 'scope': './', 'display': 'standalone', 'background_color': '#ffffff', 'theme_color': '#245c42'}
    (destination/'codexai-manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    injection = '<link rel="manifest" href="./codexai-manifest.webmanifest"><script src="./codexai-register.js" defer></script>'
    match = re.search(r'</head\s*>', html, re.I)
    html = html[:match.start()] + injection + html[match.start():] if match else injection + html
    index.write_text(html, encoding='utf-8')
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--title', required=True)
    args = parser.parse_args()
    try:
        prepare(args.archive, args.destination, args.title)
    except (ValueError, UnicodeDecodeError) as exc:
        parser.error(str(exc))
