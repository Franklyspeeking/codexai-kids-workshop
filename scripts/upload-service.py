#!/usr/bin/env python3
"""Small, local-only classroom submission and teacher publishing service."""
import csv
from contextlib import contextmanager
import hmac
import io
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEXAI_DATA_DIR', '/var/lib/codexai-uploader'))
WORKS = Path(os.environ.get('CODEXAI_WORKS_DIR', '/srv/codexai-students'))
ADMIN_TOKEN = os.environ.get('CODEXAI_ADMIN_TOKEN', '')
MAX_ZIP = 25_000_000
CODE_RE = re.compile(r'[a-z][a-z0-9-]{2,30}\Z')
CLASS_RE = re.compile(r'[a-z][a-z0-9-]{2,16}\Z')


@contextmanager
def db():
    conn = sqlite3.connect(DATA / 'classroom.sqlite3', timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    if not ADMIN_TOKEN or len(ADMIN_TOKEN) < 24:
        raise RuntimeError('CODEXAI_ADMIN_TOKEN is required and must be at least 24 characters')
    for path in (DATA, DATA / 'archives', DATA / 'prepared', WORKS / 'current', WORKS / 'releases'):
        path.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    with db() as conn:
        conn.executescript('''
          CREATE TABLE IF NOT EXISTS slots (
            code TEXT PRIMARY KEY, class_id TEXT NOT NULL, upload_token TEXT NOT NULL,
            created_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL REFERENCES slots(code),
            received_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            preview_token TEXT NOT NULL UNIQUE, published_at TEXT NOT NULL DEFAULT ''
          );
          CREATE INDEX IF NOT EXISTS submissions_code_id ON submissions(code,id DESC);
        ''')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def work_url(code):
    return f'https://codexai.site/works/{code}/money/'


class Handler(BaseHTTPRequestHandler):
    server_version = 'CodexAIClassroom/1'

    def log_message(self, fmt, *args):
        # Never log upload credentials or admin token.
        sys.stderr.write('%s %s\n' % (self.log_date_time_string(), fmt % args))

    def send_bytes(self, status, body, content_type='application/json; charset=utf-8', extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, message):
        self.send_bytes(status, {'error': message})

    def admin(self):
        provided = self.headers.get('X-Admin-Token', '')
        if not hmac.compare_digest(provided, ADMIN_TOKEN):
            self.error(401, '教师密钥不正确')
            return False
        return True

    def code_and_token(self, code):
        if not CODE_RE.fullmatch(code):
            self.error(400, '作品编号格式不正确')
            return False
        with db() as conn:
            slot = conn.execute('SELECT upload_token FROM slots WHERE code=?', (code,)).fetchone()
        if not slot or not hmac.compare_digest(self.headers.get('X-Upload-Token', ''), slot['upload_token']):
            self.error(403, '作品编号或上传码不正确，请找老师核对')
            return False
        return True

    def read_json(self, limit=4096):
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            raise ValueError('请求格式不正确')
        length = int(self.headers.get('Content-Length', '0'))
        if length < 1 or length > limit:
            raise ValueError('请求内容过大或为空')
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health':
            self.send_bytes(200, {'ok': True})
        elif path == '/api/admin/slots':
            if not self.admin(): return
            with db() as conn:
                rows = conn.execute('''SELECT slots.code,slots.class_id,slots.upload_token,
                    s.id submission_id,s.status,s.error,s.received_at,s.preview_token,s.published_at
                    FROM slots LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE code=slots.code)
                    ORDER BY slots.class_id DESC,slots.code''').fetchall()
            self.send_bytes(200, [dict(r) | {'url': work_url(r['code']) if (WORKS/'current'/r['code']).is_symlink() else None} for r in rows])
        elif path.startswith('/api/status/'):
            code = path.removeprefix('/api/status/')
            if not self.code_and_token(code): return
            with db() as conn:
                row = conn.execute('SELECT status,error,received_at FROM submissions WHERE code=? ORDER BY id DESC LIMIT 1', (code,)).fetchone()
            self.send_bytes(200, {'code': code, 'status': row['status'] if row else '未提交',
                'error': row['error'] if row else '', 'received_at': row['received_at'] if row else '',
                'url': work_url(code) if (WORKS/'current'/code).is_symlink() else None})
        elif path.startswith('/api/works/') and path.endswith('/qr.png'):
            code = path.removeprefix('/api/works/').removesuffix('/qr.png')
            if not CODE_RE.fullmatch(code) or not (WORKS/'current'/code).is_symlink():
                return self.error(404, '作品尚未发布')
            try:
                import qrcode
                image = qrcode.make(work_url(code))
                out = io.BytesIO(); image.save(out, format='PNG')
                self.send_bytes(200, out.getvalue(), 'image/png')
            except ImportError:
                self.error(503, '二维码组件尚未安装')
        elif path.startswith('/preview/'):
            self.preview(path)
        elif path == '/api/admin/roster.csv':
            if not self.admin(): return
            selected = parse_qs(urlsplit(self.path).query).get('class_id', [''])[0]
            if selected and not CLASS_RE.fullmatch(selected): return self.error(400, '班级编号格式不正确')
            with db() as conn:
                rows = conn.execute('SELECT class_id,code,upload_token FROM slots WHERE (?="" OR class_id=?) ORDER BY class_id,code', (selected,selected)).fetchall()
            out = io.StringIO(); writer = csv.writer(out)
            writer.writerow(['班级编号','作品编号','上传码','学生姓名（老师填写）','家长联系方式（老师填写）'])
            for r in rows: writer.writerow([r['class_id'],r['code'],r['upload_token'],'',''])
            self.send_bytes(200, ('\ufeff'+out.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8',
                {'Content-Disposition': 'attachment; filename="classroom-roster.csv"'})
        else:
            self.error(404, '页面不存在')

    def preview(self, path):
        # Caddy exposes this only on www.codexai.site, a separate browser origin.
        parts = path.split('/')
        if len(parts) < 3 or not re.fullmatch(r'[A-Za-z0-9_-]{32,64}', parts[2]):
            return self.error(404, '预览不存在')
        with db() as conn:
            row = conn.execute('SELECT id,status FROM submissions WHERE preview_token=?', (parts[2],)).fetchone()
        if not row or row['status'] not in ('待审核', '已发布'):
            return self.error(404, '预览不存在')
        relative = unquote('/'.join(parts[3:])) or 'index.html'
        if relative.endswith('/'): relative += 'index.html'
        pure = PurePosixPath(relative)
        if pure.is_absolute() or '..' in pure.parts or any(p.startswith('.') for p in pure.parts):
            return self.error(404, '文件不存在')
        root = DATA/'prepared'/str(row['id'])
        target = root.joinpath(*pure.parts)
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
            return self.error(404, '文件不存在')
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        self.send_bytes(200, target.read_bytes(), mime + ('; charset=utf-8' if mime.startswith('text/') or mime in ('application/javascript','application/json') else ''))

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if path == '/api/admin/classes':
                if not self.admin(): return
                body = self.read_json()
                class_id, count = body.get('class_id'), body.get('count')
                if not isinstance(class_id, str) or not CLASS_RE.fullmatch(class_id) or type(count) is not int or not 1 <= count <= 25:
                    return self.error(400, '班级编号须以小写字母开头，人数为1–25')
                codes = [f'{class_id}-s{i:02d}' for i in range(1,count+1)]
                if any(not CODE_RE.fullmatch(c) for c in codes): return self.error(400, '班级编号过长')
                rows = [(c,class_id,secrets.token_urlsafe(9),now()) for c in codes]
                with db() as conn:
                    if conn.execute('SELECT 1 FROM slots WHERE class_id=?', (class_id,)).fetchone():
                        return self.error(409, '这个班级编号已经使用，请换一个')
                    conn.executemany('INSERT INTO slots VALUES (?,?,?,?)',rows)
                self.send_bytes(201, {'created': len(rows)})
            elif path.startswith('/api/submit/'):
                self.submit(path.removeprefix('/api/submit/'))
            elif path.startswith('/api/admin/publish/'):
                if not self.admin(): return
                self.publish(path.removeprefix('/api/admin/publish/'))
            elif path.startswith('/api/admin/reject/'):
                if not self.admin(): return
                self.reject(path.removeprefix('/api/admin/reject/'))
            else:
                self.error(404, '接口不存在')
        except (ValueError, json.JSONDecodeError) as exc:
            self.error(400, str(exc))
        except Exception as exc:
            self.log_message('internal error %s', repr(exc))
            self.error(500, '服务器处理失败，请告知老师稍后重试')

    def submit(self, code):
        if not self.code_and_token(code): return
        if self.headers.get('Content-Type', '').split(';')[0] not in ('application/zip','application/octet-stream'):
            return self.error(415, '请选择 ZIP 压缩包')
        try: length = int(self.headers.get('Content-Length', '0'))
        except ValueError: length = 0
        if not 1 <= length <= MAX_ZIP: return self.error(413, '压缩包必须小于25MB')
        with tempfile.TemporaryDirectory(dir=DATA) as temp:
            temp = Path(temp)
            archive = temp/'submitted.zip'
            with archive.open('wb') as out:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024*1024,remaining))
                    if not chunk: return self.error(400, '文件传输中断，请重试')
                    out.write(chunk); remaining -= len(chunk)
            with archive.open('rb') as source: magic = source.read(4)
            if magic != b'PK\x03\x04':
                return self.error(400, '文件不是有效的 ZIP 压缩包')
            with db() as conn:
                cur = conn.execute('INSERT INTO submissions(code,received_at,status,preview_token) VALUES (?,?,?,?)',
                    (code,now(),'检查中',secrets.token_urlsafe(32)))
                sid = cur.lastrowid
            archive_dir = DATA/'archives'/code
            archive_dir.mkdir(exist_ok=True)
            shutil.copy2(archive,archive_dir/f'{sid}.zip')
            try:
                for command in (
                    [sys.executable,str(BASE/'unpack-student-zip.py'),str(archive),str(temp/'unpacked')],
                    [sys.executable,str(BASE/'package-student.py'),str(temp/'unpacked'),code,'--output',str(temp/'packages')],
                ):
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if result.returncode:
                        raise ValueError((result.stderr or result.stdout).strip()[-300:])
                shutil.move(str(temp/'packages'/code), DATA/'prepared'/str(sid))
                with db() as conn: conn.execute('UPDATE submissions SET status=? WHERE id=?',('待审核',sid))
                self.send_bytes(201, {'id':sid,'code':code,'status':'待审核','message':'上传成功，正在等待老师检查和发布'})
            except (ValueError, subprocess.TimeoutExpired) as exc:
                message = str(exc).replace('\n',' ')[:300]
                with db() as conn: conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',message,sid))
                self.error(422, '文件检查未通过：'+message)

    def publish(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        with db() as conn:
            row = conn.execute('SELECT * FROM submissions WHERE id=?',(int(id_text),)).fetchone()
            if not row: return self.error(404,'提交不存在')
            latest = conn.execute('SELECT MAX(id) FROM submissions WHERE code=?',(row['code'],)).fetchone()[0]
            if row['id'] != latest: return self.error(409,'已有更新的提交，请检查最新版本')
            if row['status'] != '待审核': return self.error(409,'这个提交不在待审核状态')
        code = row['code']; src = DATA/'prepared'/str(row['id'])
        if not (src/'money/index.html').is_file(): return self.error(409,'准备好的作品文件缺失')
        release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(row['id'])
        target = WORKS/'releases'/code/release
        target.parent.mkdir(exist_ok=True, mode=0o755)
        os.chmod(target.parent,0o755)
        shutil.copytree(src,target)
        os.chmod(target,0o755)
        for item in target.rglob('*'):
            os.chmod(item,0o755 if item.is_dir() else 0o644)
        link = WORKS/'current'/code
        next_link = WORKS/'current'/(code+'.next-'+secrets.token_hex(4))
        next_link.symlink_to(Path('../releases')/code/release)
        os.replace(next_link,link)
        with db() as conn: conn.execute('UPDATE submissions SET status=?,published_at=? WHERE id=?',('已发布',now(),row['id']))
        self.send_bytes(200,{'code':code,'status':'已发布','url':work_url(code),
            'qr':f'https://codexai.site/api/works/{code}/qr.png'})

    def reject(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        body = self.read_json()
        reason = str(body.get('reason','')).strip()[:200]
        if not reason: return self.error(400,'请填写需要修改的原因')
        with db() as conn:
            row = conn.execute('SELECT code,status FROM submissions WHERE id=?',(int(id_text),)).fetchone()
            if not row or row['status'] != '待审核': return self.error(409,'这个提交无法退回')
            if conn.execute('SELECT MAX(id) FROM submissions WHERE code=?',(row['code'],)).fetchone()[0] != int(id_text):
                return self.error(409,'已有更新的提交')
            conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',reason,int(id_text)))
        self.send_bytes(200,{'status':'需修改'})


if __name__ == '__main__':
    init()
    host = os.environ.get('CODEXAI_BIND','127.0.0.1')
    port = int(os.environ.get('CODEXAI_PORT','8766'))
    ThreadingHTTPServer((host,port),Handler).serve_forever()
