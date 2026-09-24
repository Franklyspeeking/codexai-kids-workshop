#!/usr/bin/env python3
"""Small, local-only classroom submission and teacher publishing service."""
import csv
from contextlib import contextmanager
import base64
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
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEXAI_DATA_DIR', '/var/lib/codexai-uploader'))
WORKS = Path(os.environ.get('CODEXAI_WORKS_DIR', '/srv/codexai-students'))
ADMIN_TOKEN = os.environ.get('CODEXAI_ADMIN_TOKEN', '')
MAX_ZIP = 25_000_000
CODE_RE = re.compile(r'[a-z][a-z0-9-]{2,30}\Z')
CLASS_RE = re.compile(r'[a-z][a-z0-9-]{2,16}\Z')
SLUG_RE = re.compile(r'[a-z][a-z0-9-]{2,30}\Z')
LEGACY_PROGRAM = 'workshop01'
LEGACY_LESSON = 'money'


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
    for path in (DATA, DATA / 'archives', DATA / 'prepared', DATA / 'starters',
                 WORKS / 'current', WORKS / 'releases', WORKS / 'v2/current', WORKS / 'v2/releases'):
        path.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    for path in (WORKS, WORKS / 'v2', WORKS / 'v2/current', WORKS / 'v2/releases'):
        os.chmod(path, 0o755)
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
          CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL, kind TEXT NOT NULL, days INTEGER NOT NULL,
            description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT, program_id INTEGER NOT NULL REFERENCES programs(id),
            slug TEXT NOT NULL UNIQUE, title TEXT NOT NULL, day_no INTEGER NOT NULL,
            format TEXT NOT NULL, starter_path TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS enrollments (
            code TEXT NOT NULL REFERENCES slots(code), program_id INTEGER NOT NULL REFERENCES programs(id),
            PRIMARY KEY(code,program_id)
          );
          CREATE TABLE IF NOT EXISTS published_works (
            code TEXT NOT NULL REFERENCES slots(code), lesson_id INTEGER NOT NULL REFERENCES lessons(id),
            submission_id INTEGER NOT NULL REFERENCES submissions(id), url TEXT NOT NULL,
            listed INTEGER NOT NULL DEFAULT 1, published_at TEXT NOT NULL,
            PRIMARY KEY(code,lesson_id)
          );
        ''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(submissions)')}
        if 'lesson_id' not in columns:
            conn.execute('ALTER TABLE submissions ADD COLUMN lesson_id INTEGER REFERENCES lessons(id)')
        conn.execute('INSERT OR IGNORE INTO programs(slug,title,kind,days,description,created_at) VALUES (?,?,?,?,?,?)',
                     (LEGACY_PROGRAM,'零花钱计划师','workshop',1,'半天 AI 创作工作坊首课',now()))
        program_id = conn.execute('SELECT id FROM programs WHERE slug=?',(LEGACY_PROGRAM,)).fetchone()['id']
        conn.execute('INSERT OR IGNORE INTO lessons(program_id,slug,title,day_no,format,starter_path,created_at) VALUES (?,?,?,?,?,?,?)',
                     (program_id,LEGACY_LESSON,'零花钱计划师',1,'money',
                      '/srv/codexai/current/classroom/零花钱计划师-起始包.zip',now()))
        lesson_id = conn.execute('SELECT id FROM lessons WHERE slug=?',(LEGACY_LESSON,)).fetchone()['id']
        conn.execute('UPDATE submissions SET lesson_id=? WHERE lesson_id IS NULL',(lesson_id,))
        conn.execute('INSERT OR IGNORE INTO enrollments(code,program_id) SELECT code,? FROM slots',(program_id,))
        for row in conn.execute('SELECT code,MAX(id) sid FROM submissions WHERE status=? AND lesson_id=? GROUP BY code',('已发布',lesson_id)):
            if (WORKS/'current'/row['code']).is_symlink():
                conn.execute('INSERT OR IGNORE INTO published_works(code,lesson_id,submission_id,url,listed,published_at) VALUES (?,?,?,?,?,?)',
                             (row['code'],lesson_id,row['sid'],work_url(row['code']),0 if row['code'].startswith('qa') else 1,now()))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def work_url(code):
    return f'https://codexai.site/works/{code}/money/'


def project_url(code, slug):
    return f'https://codexai.site/projects/{code}/{slug}/'


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

    def student(self):
        raw = self.headers.get('Cookie','')[:1024]
        cookie = SimpleCookie()
        try: cookie.load(raw)
        except Exception: cookie = SimpleCookie()
        value = cookie.get('codexai_student')
        if not value:
            self.error(401,'请先登录学生后台')
            return None
        try:
            payload,sig = value.value.split('.',1)
            decoded = base64.urlsafe_b64decode(payload + '='*(-len(payload)%4)).decode()
            code, expiry_text = decoded.split(':',1)
            expiry = int(expiry_text)
        except (ValueError, UnicodeDecodeError):
            self.error(401,'登录已失效，请重新登录')
            return None
        if not CODE_RE.fullmatch(code) or expiry < int(datetime.now(timezone.utc).timestamp()):
            self.error(401,'登录已失效，请重新登录')
            return None
        with db() as conn:
            row = conn.execute('SELECT upload_token FROM slots WHERE code=?',(code,)).fetchone()
        expected = hmac.new((ADMIN_TOKEN+row['upload_token']).encode(),payload.encode(),'sha256').hexdigest() if row else ''
        if not hmac.compare_digest(sig,expected):
            self.error(401,'登录已失效，请重新登录')
            return None
        return code

    def student_post_origin(self):
        if self.headers.get('Origin') != 'https://www.codexai.site':
            self.error(403,'请从学生后台提交')
            return False
        return True

    def student_lesson(self, code, lesson_id):
        with db() as conn:
            return conn.execute('''SELECT l.*,p.title program_title,p.slug program_slug,p.kind,p.days
                FROM lessons l JOIN programs p ON p.id=l.program_id
                JOIN enrollments e ON e.program_id=p.id
                WHERE l.id=? AND e.code=?''',(lesson_id,code)).fetchone()

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
        elif path == '/api/public/showcase':
            with db() as conn:
                rows = conn.execute('''SELECT w.code,w.url,w.published_at,l.title lesson_title,l.slug lesson_slug,
                    p.title program_title,p.kind FROM published_works w
                    JOIN lessons l ON l.id=w.lesson_id JOIN programs p ON p.id=l.program_id
                    WHERE w.listed=1 ORDER BY w.published_at DESC,w.code LIMIT 300''').fetchall()
            self.send_bytes(200,[dict(row) for row in rows])
        elif path == '/api/admin/catalog':
            if not self.admin(): return
            self.admin_catalog()
        elif path == '/api/admin/assignments':
            if not self.admin(): return
            self.admin_assignments()
        elif path == '/api/admin/works':
            if not self.admin(): return
            with db() as conn:
                rows = conn.execute('''SELECT w.*,l.title lesson_title,l.slug lesson_slug,p.title program_title
                    FROM published_works w JOIN lessons l ON l.id=w.lesson_id
                    JOIN programs p ON p.id=l.program_id ORDER BY w.published_at DESC,w.code''').fetchall()
            self.send_bytes(200,[dict(row) for row in rows])
        elif path == '/api/student/dashboard':
            code = self.student()
            if code: self.student_dashboard(code)
        elif path.startswith('/api/student/lessons/') and path.endswith('/starter.zip'):
            code = self.student()
            if code: self.student_starter(code,path)
        elif path.startswith('/api/projects/') and path.endswith('/qr.png'):
            self.project_qr(path)
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
                row = conn.execute('SELECT status,error,received_at FROM submissions WHERE code=? AND lesson_id=(SELECT id FROM lessons WHERE slug=?) ORDER BY id DESC LIMIT 1', (code,LEGACY_LESSON)).fetchone()
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
        # Caddy exposes this only on the public origin, apart from the teacher/student portal on www.
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

    def admin_catalog(self):
        with db() as conn:
            programs = [dict(r) for r in conn.execute('SELECT * FROM programs ORDER BY id DESC')]
            lessons = [dict(r) for r in conn.execute('SELECT * FROM lessons ORDER BY program_id,day_no,id')]
            classes = [dict(r) for r in conn.execute('SELECT class_id,COUNT(*) student_count FROM slots GROUP BY class_id ORDER BY class_id DESC')]
            enrolled = [dict(r) for r in conn.execute('''SELECT s.class_id,e.program_id,COUNT(*) student_count FROM enrollments e
                JOIN slots s ON s.code=e.code GROUP BY s.class_id,e.program_id''')]
        for lesson in lessons:
            lesson['starter_available'] = bool(lesson.pop('starter_path'))
        self.send_bytes(200,{'programs':programs,'lessons':lessons,'classes':classes,'enrollments':enrolled})

    def admin_assignments(self):
        selected = parse_qs(urlsplit(self.path).query).get('class_id',[''])[0]
        if selected and not CLASS_RE.fullmatch(selected): return self.error(400,'班级编号格式不正确')
        with db() as conn:
            rows = conn.execute('''SELECT st.code,st.class_id,st.upload_token,
                p.id program_id,p.title program_title,p.kind,p.days,
                l.id lesson_id,l.slug lesson_slug,l.title lesson_title,l.day_no,l.format,
                s.id submission_id,s.status,s.error,s.received_at,s.preview_token,
                w.url,w.listed,w.published_at
                FROM slots st JOIN enrollments e ON e.code=st.code
                JOIN programs p ON p.id=e.program_id JOIN lessons l ON l.program_id=p.id
                LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE code=st.code AND lesson_id=l.id)
                LEFT JOIN published_works w ON w.code=st.code AND w.lesson_id=l.id
                WHERE (?='' OR st.class_id=?)
                ORDER BY st.class_id DESC,p.id DESC,l.day_no,l.id,st.code''',(selected,selected)).fetchall()
        result=[]
        for row in rows:
            data=dict(row)
            data['preview_url'] = ('https://codexai.site/preview/'+data['preview_token']+
                ('/money/' if data['format']=='money' else '/')) if data['preview_token'] and data['status']=='待审核' else None
            result.append(data)
        self.send_bytes(200,result)

    def student_dashboard(self, code):
        with db() as conn:
            rows = conn.execute('''SELECT p.id program_id,p.title program_title,p.kind,p.days,p.description,
                l.id lesson_id,l.slug lesson_slug,l.title lesson_title,l.day_no,l.format,l.starter_path,
                s.status,s.error,s.received_at,w.url,w.published_at
                FROM enrollments e JOIN programs p ON p.id=e.program_id
                JOIN lessons l ON l.program_id=p.id
                LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE code=e.code AND lesson_id=l.id)
                LEFT JOIN published_works w ON w.code=e.code AND w.lesson_id=l.id
                WHERE e.code=? ORDER BY p.id DESC,l.day_no,l.id''',(code,)).fetchall()
        result=[]
        for row in rows:
            data=dict(row); data['starter_available']=bool(data.pop('starter_path')); result.append(data)
        self.send_bytes(200,{'code':code,'lessons':result})

    def student_starter(self, code, path):
        match = re.fullmatch(r'/api/student/lessons/(\d+)/starter\.zip',path)
        if not match: return self.error(404,'起始包不存在')
        lesson = self.student_lesson(code,int(match.group(1)))
        if not lesson or not lesson['starter_path']: return self.error(404,'这个课题还没有起始包')
        starter = Path(lesson['starter_path'])
        if not (starter.resolve().is_relative_to((DATA/'starters').resolve()) or
                starter.resolve().is_relative_to(Path('/srv/codexai/current/classroom').resolve())):
            return self.error(404,'起始包路径不正确')
        if not starter.is_file(): return self.error(404,'起始包暂时不可用，请联系老师')
        self.send_bytes(200,starter.read_bytes(),'application/zip',
            {'Content-Disposition':f'attachment; filename="{lesson["slug"]}-starter.zip"'})

    def project_qr(self, path):
        match = re.fullmatch(r'/api/projects/([a-z][a-z0-9-]{2,30})/([a-z][a-z0-9-]{2,30})/qr\.png',path)
        if not match: return self.error(404,'二维码不存在')
        with db() as conn:
            row = conn.execute('''SELECT w.url FROM published_works w JOIN lessons l ON l.id=w.lesson_id
                WHERE w.code=? AND l.slug=?''',match.groups()).fetchone()
        if not row: return self.error(404,'作品尚未发布')
        try:
            import qrcode
            image=qrcode.make(row['url']); output=io.BytesIO(); image.save(output,format='PNG')
            self.send_bytes(200,output.getvalue(),'image/png')
        except ImportError:
            self.error(503,'二维码组件尚未安装')

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
                    program_id = conn.execute('SELECT id FROM programs WHERE slug=?',(LEGACY_PROGRAM,)).fetchone()['id']
                    conn.executemany('INSERT INTO enrollments(code,program_id) VALUES (?,?)',[(c,program_id) for c in codes])
                self.send_bytes(201, {'created': len(rows)})
            elif path == '/api/admin/programs':
                if not self.admin(): return
                self.create_program()
            elif path == '/api/admin/lessons':
                if not self.admin(): return
                self.create_lesson()
            elif path == '/api/admin/enroll-class':
                if not self.admin(): return
                self.enroll_class()
            elif re.fullmatch(r'/api/admin/lessons/\d+/starter',path):
                if not self.admin(): return
                self.upload_starter(path)
            elif re.fullmatch(r'/api/admin/visibility/[a-z][a-z0-9-]{2,30}/\d+',path):
                if not self.admin(): return
                self.visibility(path)
            elif path == '/api/student/login':
                if not self.student_post_origin(): return
                self.student_login()
            elif path == '/api/student/logout':
                if not self.student_post_origin(): return
                self.send_bytes(200,{'ok':True},extra={'Set-Cookie':'codexai_student=; Path=/api/student; Max-Age=0; HttpOnly; Secure; SameSite=Strict'})
            elif re.fullmatch(r'/api/student/submit/\d+',path):
                if not self.student_post_origin(): return
                code = self.student()
                if code: self.submit(code,int(path.rsplit('/',1)[1]),authenticated=True)
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

    def create_program(self):
        body = self.read_json()
        slug,title,kind,days = body.get('slug'),body.get('title'),body.get('kind'),body.get('days')
        description = str(body.get('description','')).strip()
        if not isinstance(slug,str) or not SLUG_RE.fullmatch(slug) or not isinstance(title,str) or not 2 <= len(title.strip()) <= 60 or kind not in ('workshop','camp') or type(days) is not int or not 1 <= days <= 30 or len(description)>500:
            return self.error(400,'请填写有效的课程代号、标题、类型和1–30天的天数')
        with db() as conn:
            if conn.execute('SELECT 1 FROM programs WHERE slug=?',(slug,)).fetchone():
                return self.error(409,'课程代号已存在')
            cur=conn.execute('INSERT INTO programs(slug,title,kind,days,description,created_at) VALUES (?,?,?,?,?,?)',
                             (slug,title.strip(),kind,days,description,now()))
            program_id=cur.lastrowid
        self.send_bytes(201,{'id':program_id,'slug':slug})

    def create_lesson(self):
        body=self.read_json()
        program_id,slug,title,day_no=body.get('program_id'),body.get('slug'),body.get('title'),body.get('day_no')
        if type(program_id) is not int or not isinstance(slug,str) or not SLUG_RE.fullmatch(slug) or not isinstance(title,str) or not 2<=len(title.strip())<=60 or type(day_no) is not int:
            return self.error(400,'课题信息不完整')
        with db() as conn:
            program=conn.execute('SELECT days FROM programs WHERE id=?',(program_id,)).fetchone()
            if not program or not 1<=day_no<=program['days']: return self.error(400,'课题天数超出课程范围')
            if conn.execute('SELECT 1 FROM lessons WHERE slug=?',(slug,)).fetchone():
                return self.error(409,'课题代号已存在，请使用不同代号')
            cur=conn.execute('INSERT INTO lessons(program_id,slug,title,day_no,format,created_at) VALUES (?,?,?,?,?,?)',
                             (program_id,slug,title.strip(),day_no,'web',now()))
            lesson_id=cur.lastrowid
        self.send_bytes(201,{'id':lesson_id,'slug':slug})

    def enroll_class(self):
        body=self.read_json()
        class_id,program_id=body.get('class_id'),body.get('program_id')
        if not isinstance(class_id,str) or not CLASS_RE.fullmatch(class_id) or type(program_id) is not int:
            return self.error(400,'班级或课程信息不正确')
        with db() as conn:
            if not conn.execute('SELECT 1 FROM programs WHERE id=?',(program_id,)).fetchone():
                return self.error(404,'课程不存在')
            codes=[row['code'] for row in conn.execute('SELECT code FROM slots WHERE class_id=?',(class_id,))]
            if not codes: return self.error(404,'班级不存在')
            conn.executemany('INSERT OR IGNORE INTO enrollments(code,program_id) VALUES (?,?)',
                             [(code,program_id) for code in codes])
        self.send_bytes(200,{'enrolled':len(codes)})

    def visibility(self,path):
        match=re.fullmatch(r'/api/admin/visibility/([a-z][a-z0-9-]{2,30})/(\d+)',path)
        body=self.read_json()
        if type(body.get('listed')) is not bool: return self.error(400,'请选择是否在作品展显示')
        code,lesson_id=match.group(1),int(match.group(2))
        with db() as conn:
            cur=conn.execute('UPDATE published_works SET listed=? WHERE code=? AND lesson_id=?',
                             (int(body['listed']),code,lesson_id))
            if cur.rowcount!=1: return self.error(404,'已发布作品不存在')
        self.send_bytes(200,{'listed':body['listed']})

    def student_login(self):
        body=self.read_json()
        code,token=body.get('code'),body.get('token')
        if not isinstance(code,str) or not CODE_RE.fullmatch(code) or not isinstance(token,str):
            return self.error(400,'请输入作品编号和访问码')
        with db() as conn:
            row=conn.execute('SELECT upload_token FROM slots WHERE code=?',(code,)).fetchone()
        if not row or not hmac.compare_digest(token,row['upload_token']):
            return self.error(403,'编号或访问码不正确')
        expiry=int(datetime.now(timezone.utc).timestamp())+7*24*3600
        payload=base64.urlsafe_b64encode(f'{code}:{expiry}'.encode()).decode().rstrip('=')
        signature=hmac.new((ADMIN_TOKEN+token).encode(),payload.encode(),'sha256').hexdigest()
        cookie=f'codexai_student={payload}.{signature}; Path=/api/student; Max-Age=604800; HttpOnly; Secure; SameSite=Strict'
        self.send_bytes(200,{'code':code},extra={'Set-Cookie':cookie})

    def upload_starter(self,path):
        lesson_id=int(path.split('/')[4])
        with db() as conn:
            lesson=conn.execute('SELECT title,format FROM lessons WHERE id=?',(lesson_id,)).fetchone()
        if not lesson or lesson['format']!='web': return self.error(400,'只支持给通用网页课题上传起始包')
        if self.headers.get('Content-Type','').split(';')[0] not in ('application/zip','application/octet-stream'):
            return self.error(415,'请选择 ZIP 压缩包')
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: length=0
        if not 1<=length<=MAX_ZIP: return self.error(413,'起始包须小于25MB')
        with tempfile.TemporaryDirectory(dir=DATA) as scratch:
            scratch=Path(scratch); archive=scratch/'starter.zip'
            with archive.open('wb') as output:
                remaining=length
                while remaining:
                    chunk=self.rfile.read(min(1024*1024,remaining))
                    if not chunk: return self.error(400,'上传中断，请重试')
                    output.write(chunk); remaining-=len(chunk)
            result=subprocess.run([sys.executable,str(BASE/'prepare-web-zip.py'),str(archive),str(scratch/'checked'),
                                   '--title',lesson['title']],capture_output=True,text=True,timeout=30)
            if result.returncode:
                return self.error(422,'起始包检查未通过：'+(result.stderr or result.stdout).strip()[-250:])
            target=DATA/'starters'/f'{lesson_id}.zip'
            shutil.copy2(archive,target)
            with db() as conn: conn.execute('UPDATE lessons SET starter_path=? WHERE id=?',(str(target),lesson_id))
        self.send_bytes(200,{'lesson_id':lesson_id,'starter_available':True})

    def submit(self, code, lesson_id=None, authenticated=False):
        if not authenticated and not self.code_and_token(code): return
        if lesson_id is None:
            with db() as conn:
                lesson_id=conn.execute('SELECT id FROM lessons WHERE slug=?',(LEGACY_LESSON,)).fetchone()['id']
        lesson=self.student_lesson(code,lesson_id)
        if not lesson: return self.error(403,'这个课题尚未分配给你')
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
                cur = conn.execute('INSERT INTO submissions(code,received_at,status,preview_token,lesson_id) VALUES (?,?,?,?,?)',
                    (code,now(),'检查中',secrets.token_urlsafe(32),lesson_id))
                sid = cur.lastrowid
            archive_dir = DATA/'archives'/code
            archive_dir.mkdir(exist_ok=True)
            shutil.copy2(archive,archive_dir/f'{sid}.zip')
            try:
                commands = ([sys.executable,str(BASE/'unpack-student-zip.py'),str(archive),str(temp/'unpacked')],
                            [sys.executable,str(BASE/'package-student.py'),str(temp/'unpacked'),code,'--output',str(temp/'packages')]) \
                           if lesson['format']=='money' else ([sys.executable,str(BASE/'prepare-web-zip.py'),
                            str(archive),str(temp/'packages'/code),'--title',lesson['title']],)
                for command in commands:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if result.returncode:
                        raise ValueError((result.stderr or result.stdout).strip()[-300:])
                shutil.move(str(temp/'packages'/code), DATA/'prepared'/str(sid))
                with db() as conn: conn.execute('UPDATE submissions SET status=? WHERE id=?',('待审核',sid))
                self.send_bytes(201, {'id':sid,'code':code,'lesson_id':lesson_id,'status':'待审核','message':'上传成功，正在等待老师检查和发布'})
            except (ValueError, subprocess.TimeoutExpired) as exc:
                message = str(exc).replace('\n',' ')[:300]
                with db() as conn: conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',message,sid))
                self.error(422, '文件检查未通过：'+message)

    def publish(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        with db() as conn:
            row = conn.execute('''SELECT s.*,l.format,l.slug,l.title FROM submissions s
                JOIN lessons l ON l.id=s.lesson_id WHERE s.id=?''',(int(id_text),)).fetchone()
            if not row: return self.error(404,'提交不存在')
            latest = conn.execute('SELECT MAX(id) FROM submissions WHERE code=? AND lesson_id=?',
                                  (row['code'],row['lesson_id'])).fetchone()[0]
            if row['id'] != latest: return self.error(409,'已有更新的提交，请检查最新版本')
            if row['status'] != '待审核': return self.error(409,'这个提交不在待审核状态')
        code = row['code']; src = DATA/'prepared'/str(row['id'])
        required = src/'money/index.html' if row['format']=='money' else src/'index.html'
        if not required.is_file(): return self.error(409,'准备好的作品文件缺失')
        release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(row['id'])
        if row['format']=='money':
            target = WORKS/'releases'/code/release
            link = WORKS/'current'/code
            link_target = Path('../releases')/code/release
            url = work_url(code)
        else:
            target = WORKS/'v2/releases'/code/row['slug']/release
            link = WORKS/'v2/current'/code/row['slug']
            link_target = Path('../../releases')/code/row['slug']/release
            url = project_url(code,row['slug'])
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if row['format']!='money': os.chmod(target.parent.parent,0o755)
        os.chmod(target.parent,0o755)
        shutil.copytree(src,target)
        os.chmod(target,0o755)
        for item in target.rglob('*'):
            os.chmod(item,0o755 if item.is_dir() else 0o644)
        link.parent.mkdir(exist_ok=True,mode=0o755)
        os.chmod(link.parent,0o755)
        next_link = link.parent/(link.name+'.next-'+secrets.token_hex(4))
        next_link.symlink_to(link_target)
        os.replace(next_link,link)
        published_at=now()
        with db() as conn:
            conn.execute('UPDATE submissions SET status=?,published_at=? WHERE id=?',('已发布',published_at,row['id']))
            conn.execute('''INSERT INTO published_works(code,lesson_id,submission_id,url,listed,published_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(code,lesson_id) DO UPDATE SET
                submission_id=excluded.submission_id,url=excluded.url,published_at=excluded.published_at''',
                (code,row['lesson_id'],row['id'],url,0 if code.startswith('qa') else 1,published_at))
        qr=(f'https://codexai.site/api/works/{code}/qr.png' if row['format']=='money' else
            f'https://codexai.site/api/projects/{code}/{row["slug"]}/qr.png')
        self.send_bytes(200,{'code':code,'lesson_id':row['lesson_id'],'status':'已发布','url':url,'qr':qr})

    def reject(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        body = self.read_json()
        reason = str(body.get('reason','')).strip()[:200]
        if not reason: return self.error(400,'请填写需要修改的原因')
        with db() as conn:
            row = conn.execute('SELECT code,lesson_id,status FROM submissions WHERE id=?',(int(id_text),)).fetchone()
            if not row or row['status'] != '待审核': return self.error(409,'这个提交无法退回')
            if conn.execute('SELECT MAX(id) FROM submissions WHERE code=? AND lesson_id=?',
                            (row['code'],row['lesson_id'])).fetchone()[0] != int(id_text):
                return self.error(409,'已有更新的提交')
            conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',reason,int(id_text)))
        self.send_bytes(200,{'status':'需修改'})


if __name__ == '__main__':
    init()
    host = os.environ.get('CODEXAI_BIND','127.0.0.1')
    port = int(os.environ.get('CODEXAI_PORT','8766'))
    ThreadingHTTPServer((host,port),Handler).serve_forever()
