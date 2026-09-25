#!/usr/bin/env python3
"""Small, local-only classroom submission and teacher publishing service."""
import csv
from contextlib import contextmanager
import base64
import hashlib
import hmac
import html
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
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, unquote, urlsplit
from xml.sax.saxutils import escape as xml_escape

BASE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('CODEXAI_DATA_DIR', '/var/lib/codexai-uploader'))
WORKS = Path(os.environ.get('CODEXAI_WORKS_DIR', '/srv/codexai-students'))
ADMIN_TOKEN = os.environ.get('CODEXAI_ADMIN_TOKEN', '')
MIN_ADMIN_PASSWORD_LENGTH = 7
PUBLIC_ORIGIN = os.environ.get('CODEXAI_PUBLIC_ORIGIN', 'https://www.codexai.site').rstrip('/')
STATIC_DIR_VALUE = os.environ.get('CODEXAI_STATIC_DIR', '')
STATIC_DIR = Path(STATIC_DIR_VALUE).resolve() if STATIC_DIR_VALUE else None
MAX_ZIP = 25_000_000
CODE_RE = re.compile(r'[a-z][a-z0-9-]{2,30}\Z')
CLASS_RE = re.compile(r'[a-z][a-z0-9-]{2,16}\Z')
SLUG_RE = re.compile(r'[a-z][a-z0-9-]{2,30}\Z')
LEGACY_PROGRAM = 'workshop01'
LEGACY_LESSON = 'money'
TEACHER_INTRO = (
    '你好，我是 Code-X-Ai 的创建者。我不是 IT 专业出身。正因为如此，我更能体会普通人刚接触 AI 时的疑问：从哪里开始？怎样提问？AI 给出的答案能不能相信？这些工具又能怎样帮到自己？\n\n'
    '我建立 Code-X-Ai，是希望用通俗的语言和动手练习，让 AI 成为普通人也能用得上的工具。对孩子来说，学习 AI 不只是学会操作，更是学会借助工具探索问题、表达想法，同时保持独立思考，懂得核对信息和保护隐私。\n\n'
    '我会持续学习、实践和更新内容，把自己弄明白的方法认真分享出来。希望家长看得清孩子在学什么，孩子也能一步步学会把 AI 用好。'
)
DEFAULT_FAQS = [
    {'q':'孩子没有编程基础，能参加吗？','a':'可以。首课面向 9–16 岁零基础孩子，使用老师准备的可运行起始包。孩子要练习的是说明需求、做选择和测试结果。'},
    {'q':'需要自己带电脑吗？','a':'孩子需要带笔记本电脑参加。具体浏览器与 AI 工具的登录、网络要求，报名后由老师提前告知并协助检查。'},
    {'q':'半天能做完什么？','a':'首课约 3.5 小时。孩子完成一个可在浏览器打开的零花钱网页工具，并能向家长介绍目标、规则和改动。不同孩子的功能与完成程度会有差异。'},
    {'q':'作品是孩子做的，还是 AI 直接生成的？','a':'AI 负责协助实现，孩子要决定问题、规则、页面和测试标准。课堂会保留需求卡、修改与测试过程，老师会引导孩子解释自己的选择。'},
    {'q':'家长怎么收到作品？能放手机桌面吗？','a':'老师审核后提供专属网址和二维码。家长在手机浏览器打开，再使用“添加到主屏幕”。首次打开要联网；桌面使用和离线能力要在实际手机上测试。'},
    {'q':'孩子以后还能继续上传自己的作品吗？','a':'能。已报名学生沿用老师创建的账号，可以继续上传课程作品，或创建课后的独立网页作品。每次新版本仍需老师审核。'},
    {'q':'作品会自动公开吗？','a':'不会。通过审核后先得到给家长的非公开分享链接；只有老师线下取得家长同意并登记后，作品才可能进入公开展。分享链接可由持有者转发，必要时可联系老师撤销。'},
    {'q':'作品会保留多久？换手机怎么办？','a':'平台计划长期保存作品文件和已发布版本，并定期备份。零花钱等工具里的个人记录留在家长使用的那部手机浏览器；换机或清理数据前应自行导出备份。'},
    {'q':'其他八个主题什么时候开课？','a':'它们目前是课程方向，尚未公布具体排期。网站只对已标为开放咨询的课程提供报名咨询；可联系老师了解后续更新。'},
]
DEFAULT_COURSES = [
    {
        'slug':'chores','title':'家务积分银行','lesson_slug':'chores-tool',
        'description':'把家务规则变成孩子参与设计、全家都看得懂的积分工具。',
        'summary':'孩子设计任务、积分和兑换规则，在真实家庭情景中检查规则是否公平。',
        'outcome':'一套可调整任务与奖励规则的家务积分网页工具',
        'parent_role':'家长和孩子一起试用规则，讨论怎样分工更公平',
    },
    {
        'slug':'weekend','title':'周末时间调度员','lesson_slug':'weekend-planner',
        'description':'把想做的事排进周末，也学会为休息和变化留出空间。',
        'summary':'孩子安排活动、发现时间冲突并比较方案，做自己的周末日程工具。',
        'outcome':'一份能发现冲突、调整顺序的周末日程网页工具',
        'parent_role':'家长提供家庭安排，和孩子一起比较并确认周末方案',
    },
    {
        'slug':'screen-time','title':'屏幕时间协商器','lesson_slug':'screen-time-agreement',
        'description':'把“能不能再玩一会儿”变成双方都能参与的清楚约定。',
        'summary':'孩子表达自己的需要，也听见家长的担心，共同设计可执行的屏幕时间约定。',
        'outcome':'一份可记录、复盘和调整的家庭屏幕时间协商工具',
        'parent_role':'家长提出边界和原因，与孩子共同试用并复盘约定',
    },
    {
        'slug':'family-trip','title':'家庭旅行合伙人','lesson_slug':'family-trip-planner',
        'description':'从“我想去哪儿”开始，比较路线、预算和全家人的偏好。',
        'summary':'孩子收集家人的旅行偏好，比较时间与预算，提出有理由的旅行方案。',
        'outcome':'一份能收集偏好、比较方案的家庭旅行规划网页工具',
        'parent_role':'家长提供真实约束，让孩子解释并完善自己的旅行提案',
    },
    {
        'slug':'healthy-habits','title':'健康习惯挑战板','lesson_slug':'habit-challenge',
        'description':'让微小行动被看见，把“坚持”设计成每天都能完成的挑战。',
        'summary':'孩子选择自己的小目标、打卡方式和鼓励规则，观察怎样更容易坚持。',
        'outcome':'一块带目标、打卡和自定义鼓励规则的习惯挑战板',
        'parent_role':'家长陪孩子选择小而可行的目标，用鼓励代替催促',
    },
    {
        'slug':'recycling','title':'垃圾分类挑战赛','lesson_slug':'recycling-quiz',
        'description':'孩子自己当出题人，把环保知识做成一场能玩的挑战赛。',
        'summary':'孩子查找并核对分类知识，设计题目、提示和计分规则，再邀请家人闯关。',
        'outcome':'一套包含原创题目、反馈和计分规则的垃圾分类游戏',
        'parent_role':'家长作为第一位玩家，帮助孩子发现题目是否清楚准确',
    },
    {
        'slug':'book-swap','title':'家庭阅读交换站','lesson_slug':'book-exchange',
        'description':'让读过的好书继续旅行，也让推荐理由比书名更有温度。',
        'summary':'孩子整理书架、设计借还规则并写阅读推荐，做家庭里的图书交换站。',
        'outcome':'一个能管理书架、借还和阅读推荐的家庭网页工具',
        'parent_role':'家长贡献家庭书单，和孩子一起制定容易执行的借还规则',
    },
    {
        'slug':'story-director','title':'AI 互动故事导演','lesson_slug':'interactive-story',
        'description':'不是只读故事，而是亲手决定人物、选择和每一种结局。',
        'summary':'孩子设计角色、分支和结局，用测试找出故事断点，让读者参与剧情。',
        'outcome':'一个可以选择剧情路线、拥有不同结局的互动故事网页',
        'parent_role':'家长试玩不同路线，听孩子讲述设计取舍和修改过程',
    },
]


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
    if not ADMIN_TOKEN or len(ADMIN_TOKEN) < MIN_ADMIN_PASSWORD_LENGTH:
        raise RuntimeError(
            f'CODEXAI_ADMIN_TOKEN is required and must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters'
        )
    for path in (DATA, DATA / 'archives', DATA / 'prepared', DATA / 'starters', DATA/'site',
                 WORKS / 'current', WORKS / 'releases', WORKS / 'v2/current', WORKS / 'v2/releases',
                 WORKS / 'free/current', WORKS / 'free/releases'):
        path.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    for path in (WORKS, WORKS / 'v2', WORKS / 'v2/current', WORKS / 'v2/releases',
                 WORKS / 'free', WORKS / 'free/current', WORKS / 'free/releases'):
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
            description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            marketing_status TEXT NOT NULL DEFAULT 'draft',
            marketing_summary TEXT NOT NULL DEFAULT '',
            marketing_audience TEXT NOT NULL DEFAULT '',
            marketing_outcome TEXT NOT NULL DEFAULT '',
            marketing_duration TEXT NOT NULL DEFAULT '',
            marketing_parent_role TEXT NOT NULL DEFAULT ''
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
            listed INTEGER NOT NULL DEFAULT 0, published_at TEXT NOT NULL,
            share_token TEXT UNIQUE, share_active INTEGER NOT NULL DEFAULT 1,
            legacy_allowed INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(code,lesson_id)
          );
          CREATE TABLE IF NOT EXISTS independent_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL REFERENCES slots(code),
            title TEXT NOT NULL, summary TEXT NOT NULL, category TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            published_submission_id INTEGER REFERENCES submissions(id),
            share_token TEXT UNIQUE, share_active INTEGER NOT NULL DEFAULT 0,
            listed INTEGER NOT NULL DEFAULT 0
          );
          CREATE INDEX IF NOT EXISTS independent_projects_code ON independent_projects(code,id DESC);
          CREATE TABLE IF NOT EXISTS public_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL REFERENCES slots(code),
            lesson_id INTEGER REFERENCES lessons(id),
            independent_id INTEGER REFERENCES independent_projects(id),
            submission_id INTEGER REFERENCES submissions(id),
            guardian_ref TEXT NOT NULL, channel TEXT NOT NULL, consent_at TEXT NOT NULL,
            evidence_ref TEXT NOT NULL, recorded_at TEXT NOT NULL,
            revoked_at TEXT NOT NULL DEFAULT '',
            CHECK ((lesson_id IS NOT NULL) != (independent_id IS NOT NULL))
          );
          CREATE INDEX IF NOT EXISTS public_consents_work ON public_consents(code,lesson_id,independent_id,id DESC);
          CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, parent_name TEXT NOT NULL,
            contact_kind TEXT NOT NULL, contact TEXT NOT NULL,
            child_age TEXT NOT NULL, interest TEXT NOT NULL, message TEXT NOT NULL,
            source TEXT NOT NULL, entry_path TEXT NOT NULL, ip_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '新咨询', note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS consultations_ip_time ON consultations(ip_hash,created_at DESC);
          CREATE INDEX IF NOT EXISTS consultations_status_time ON consultations(status,created_at DESC);
          CREATE TABLE IF NOT EXISTS publication_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL,
            lesson_id INTEGER, independent_id INTEGER, submission_id INTEGER NOT NULL,
            action TEXT NOT NULL, created_at TEXT NOT NULL
          );
          CREATE INDEX IF NOT EXISTS publication_events_work ON publication_events(code,lesson_id,independent_id,id DESC);
          CREATE TABLE IF NOT EXISTS site_settings (
            name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS camp_collections (
            code TEXT NOT NULL REFERENCES slots(code),
            program_id INTEGER NOT NULL REFERENCES programs(id),
            token TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(code,program_id)
          );
        ''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(submissions)')}
        if 'lesson_id' not in columns:
            conn.execute('ALTER TABLE submissions ADD COLUMN lesson_id INTEGER REFERENCES lessons(id)')
        if 'independent_id' not in columns:
            conn.execute('ALTER TABLE submissions ADD COLUMN independent_id INTEGER REFERENCES independent_projects(id)')
        program_columns = {row['name'] for row in conn.execute('PRAGMA table_info(programs)')}
        marketing_is_new = 'marketing_status' not in program_columns
        for name in ('marketing_status','marketing_summary','marketing_audience','marketing_outcome',
                     'marketing_duration','marketing_parent_role'):
            if name not in program_columns:
                default = 'draft' if name == 'marketing_status' else ''
                conn.execute(f"ALTER TABLE programs ADD COLUMN {name} TEXT NOT NULL DEFAULT '{default}'")
        consent_columns = {row['name'] for row in conn.execute('PRAGMA table_info(public_consents)')}
        if 'submission_id' not in consent_columns:
            conn.execute('ALTER TABLE public_consents ADD COLUMN submission_id INTEGER REFERENCES submissions(id)')
        published_columns = {row['name'] for row in conn.execute('PRAGMA table_info(published_works)')}
        if 'share_token' not in published_columns:
            conn.execute('ALTER TABLE published_works ADD COLUMN share_token TEXT')
            conn.execute('ALTER TABLE published_works ADD COLUMN share_active INTEGER NOT NULL DEFAULT 1')
            conn.execute('ALTER TABLE published_works ADD COLUMN legacy_allowed INTEGER NOT NULL DEFAULT 1')
            # Existing gallery decisions have no guardian-consent record. Hide them until recorded.
            conn.execute('UPDATE published_works SET listed=0')
        for row in conn.execute('SELECT code,lesson_id FROM published_works WHERE share_token IS NULL'):
            token = secrets.token_urlsafe(32)
            conn.execute('UPDATE published_works SET share_token=?,url=? WHERE code=? AND lesson_id=?',
                         (token,share_url(token),row['code'],row['lesson_id']))
        conn.execute('''INSERT OR IGNORE INTO programs
            (slug,title,kind,days,description,created_at,marketing_status,marketing_summary,
             marketing_audience,marketing_outcome,marketing_duration,marketing_parent_role)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (LEGACY_PROGRAM,'零花钱计划师','workshop',1,'半天 AI 创作工作坊首课',now(),
             'consulting','孩子为自己的小愿望制作零花钱记录与计划工具。','9–16 岁，零基础可参加',
             '一个能在家长手机打开并添加到桌面的网页工具','约 3.5 小时','家长在课后接收链接、扫码测试作品'))
        if marketing_is_new:
            conn.execute("UPDATE programs SET marketing_status='consulting' WHERE slug=?",(LEGACY_PROGRAM,))
        for name,value in [('faqs',json.dumps(DEFAULT_FAQS,ensure_ascii=False)),('teacher_intro',TEACHER_INTRO),
                           ('demo_title','零花钱计划师'),
                           ('demo_summary','设定一个小愿望，试试收入、支出和储蓄进度怎样记录。')]:
            conn.execute('INSERT OR IGNORE INTO site_settings(name,value,updated_at) VALUES (?,?,?)',(name,value,now()))
        conn.execute("UPDATE site_settings SET value=?,updated_at=? WHERE name='teacher_intro' AND value=''",(TEACHER_INTRO,now()))
        program_id = conn.execute('SELECT id FROM programs WHERE slug=?',(LEGACY_PROGRAM,)).fetchone()['id']
        conn.execute('INSERT OR IGNORE INTO lessons(program_id,slug,title,day_no,format,starter_path,created_at) VALUES (?,?,?,?,?,?,?)',
                     (program_id,LEGACY_LESSON,'零花钱计划师',1,'money',
                      '/srv/codexai/current/classroom/零花钱计划师-起始包.zip',now()))
        lesson_id = conn.execute('SELECT id FROM lessons WHERE slug=?',(LEGACY_LESSON,)).fetchone()['id']
        conn.execute('UPDATE submissions SET lesson_id=? WHERE lesson_id IS NULL',(lesson_id,))
        conn.execute('INSERT OR IGNORE INTO enrollments(code,program_id) SELECT code,? FROM slots',(program_id,))
        for course in DEFAULT_COURSES:
            conn.execute('''INSERT OR IGNORE INTO programs
                (slug,title,kind,days,description,created_at,marketing_status,marketing_summary,
                 marketing_audience,marketing_outcome,marketing_duration,marketing_parent_role)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (course['slug'],course['title'],'workshop',1,course['description'],now(),'draft',
                 course['summary'],'9–16 岁，零基础可参加',course['outcome'],'约 3.5 小时',
                 course['parent_role']))
            course_id = conn.execute('SELECT id FROM programs WHERE slug=?',(course['slug'],)).fetchone()['id']
            conn.execute('''INSERT OR IGNORE INTO lessons
                (program_id,slug,title,day_no,format,starter_path,created_at) VALUES (?,?,?,?,?,?,?)''',
                (course_id,course['lesson_slug'],course['title'],1,'web','',now()))
        for row in conn.execute('SELECT code,MAX(id) sid FROM submissions WHERE status=? AND lesson_id=? GROUP BY code',('已发布',lesson_id)):
            if (WORKS/'current'/row['code']).is_symlink() or (WORKS/'current'/row['code']).is_dir():
                token = secrets.token_urlsafe(32)
                conn.execute('''INSERT OR IGNORE INTO published_works
                    (code,lesson_id,submission_id,url,listed,published_at,share_token,legacy_allowed)
                    VALUES (?,?,?,?,?,?,?,1)''',
                    (row['code'],lesson_id,row['sid'],share_url(token),0,now(),token))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def work_url(code):
    return f'https://codexai.site/works/{code}/money/'


def activate_release(link, link_target, target):
    """Switch the current release; copy on Windows without symlink privileges."""
    next_path = link.parent/(link.name+'.next-'+secrets.token_hex(4))
    try:
        next_path.symlink_to(link_target)
        os.replace(next_path,link)
        return
    except OSError:
        if next_path.is_symlink() or next_path.is_file():
            next_path.unlink(missing_ok=True)
        elif next_path.is_dir():
            shutil.rmtree(next_path)
    shutil.copytree(target,next_path)
    if link.is_symlink() or link.is_file():
        link.unlink(missing_ok=True)
    elif link.is_dir():
        shutil.rmtree(link)
    os.replace(next_path,link)


def project_url(code, slug):
    return f'https://codexai.site/projects/{code}/{slug}/'


def share_url(token):
    return f'https://codexai.site/share/{token}/'


def gallery_url(token):
    return f'https://codexai.site/gallery/{token}/'


def collection_url(token):
    return f'https://codexai.site/collection/{token}/'


def qr_url(token):
    return f'https://codexai.site/api/share/{token}/qr.png'


class Handler(BaseHTTPRequestHandler):
    server_version = 'CodexAIClassroom/1'

    def log_message(self, fmt, *args):
        # Share and preview URLs are capability secrets; never print their tokens.
        line=fmt % args
        line=re.sub(r'/(?:api/)?share/[A-Za-z0-9_-]{32,64}',
                    '/share/<redacted>',line)
        line=re.sub(r'/gallery/[A-Za-z0-9_-]{32,64}',
                    '/gallery/<redacted>',line)
        line=re.sub(r'/collection/[A-Za-z0-9_-]{32,64}',
                    '/collection/<redacted>',line)
        line=re.sub(r'/preview/[A-Za-z0-9_-]{32,64}',
                    '/preview/<redacted>',line)
        sys.stderr.write('%s %s\n' % (self.log_date_time_string(),line))

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
            self.error(401, '教师账号或管理密码不正确')
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
        if self.headers.get('Origin') != PUBLIC_ORIGIN:
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
            try:
                with db() as conn:
                    conn.execute('SELECT 1 FROM consultations LIMIT 1').fetchone()
                    conn.execute('SELECT 1 FROM published_works LIMIT 1').fetchone()
                self.send_bytes(200, {'ok': True})
            except sqlite3.DatabaseError:
                self.error(503,'数据库暂时不可用')
        elif path == '/api/public/courses':
            self.public_courses()
        elif path == '/api/public/site-content':
            self.site_content()
        elif path == '/api/public/wechat-qr':
            self.public_wechat_qr()
        elif re.fullmatch(r'/courses/[a-z][a-z0-9-]{2,30}/',path):
            self.public_course_page(path.split('/')[2])
        elif path == '/sitemap.xml':
            self.public_sitemap()
        elif path == '/api/public/showcase':
            with db() as conn:
                rows = [dict(row) for row in conn.execute('''SELECT w.code,
                    ('https://codexai.site/gallery/'||w.share_token||'/') url,w.published_at,l.title lesson_title,l.slug lesson_slug,
                    p.title program_title,p.kind,'' summary FROM published_works w
                    JOIN lessons l ON l.id=w.lesson_id JOIN programs p ON p.id=l.program_id
                    WHERE w.listed=1 AND w.share_active=1 AND EXISTS
                    (SELECT 1 FROM public_consents c WHERE c.code=w.code AND c.lesson_id=w.lesson_id
                     AND c.submission_id=w.submission_id AND c.revoked_at='')''')]
                rows += [dict(row) for row in conn.execute('''SELECT f.code,
                    ('https://codexai.site/gallery/'||f.share_token||'/') url,
                    s.published_at,f.title lesson_title,'' lesson_slug,'自由创作' program_title,'free' kind,
                    f.summary
                    FROM independent_projects f JOIN submissions s ON s.id=f.published_submission_id
                    WHERE f.listed=1 AND f.share_active=1 AND EXISTS
                    (SELECT 1 FROM public_consents c WHERE c.code=f.code AND c.independent_id=f.id
                     AND c.submission_id=f.published_submission_id AND c.revoked_at='')''')]
            self.send_bytes(200,sorted(rows,key=lambda row:row['published_at'],reverse=True)[:300])
        elif path == '/api/admin/catalog':
            if not self.admin(): return
            self.admin_catalog()
        elif path == '/api/admin/site-content':
            if not self.admin(): return
            self.site_content()
        elif path == '/api/admin/collections':
            if not self.admin(): return
            self.admin_collections()
        elif path == '/api/admin/publication-events':
            if not self.admin(): return
            self.admin_publication_events()
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
        elif path == '/api/admin/independent':
            if not self.admin(): return
            self.admin_independent()
        elif path == '/api/admin/consents':
            if not self.admin(): return
            self.admin_consents()
        elif path == '/api/admin/consultations':
            if not self.admin(): return
            self.admin_consultations()
        elif path == '/api/admin/consultations.csv':
            if not self.admin(): return
            self.export_consultations()
        elif path == '/api/admin/versions':
            if not self.admin(): return
            self.admin_versions()
        elif path == '/api/student/dashboard':
            code = self.student()
            if code: self.student_dashboard(code)
        elif path == '/api/student/independent':
            code = self.student()
            if code: self.student_independent(code)
        elif path.startswith('/api/student/lessons/') and path.endswith('/starter.zip'):
            code = self.student()
            if code: self.student_starter(code,path)
        elif path.startswith('/api/projects/') and path.endswith('/qr.png'):
            self.project_qr(path)
        elif re.fullmatch(r'/api/share/[A-Za-z0-9_-]{32,64}/qr\.png',path):
            self.share_qr(path)
        elif path == '/api/admin/slots':
            if not self.admin(): return
            with db() as conn:
                rows = conn.execute('''SELECT slots.code,slots.class_id,slots.upload_token,
                    s.id submission_id,s.status,s.error,s.received_at,s.preview_token,s.published_at
                    FROM slots LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE code=slots.code)
                    ORDER BY slots.class_id DESC,slots.code''').fetchall()
                published={row['code']:row for row in conn.execute('''SELECT w.code,w.share_token,w.share_active
                    FROM published_works w JOIN lessons l ON l.id=w.lesson_id WHERE l.slug=?''',(LEGACY_LESSON,))}
            self.send_bytes(200, [dict(r) | {'url': share_url(published[r['code']]['share_token'])
                if r['code'] in published and published[r['code']]['share_active'] and published[r['code']]['share_token'] else None}
                for r in rows])
        elif path.startswith('/api/status/'):
            code = path.removeprefix('/api/status/')
            if not self.code_and_token(code): return
            with db() as conn:
                row = conn.execute('SELECT status,error,received_at FROM submissions WHERE code=? AND lesson_id=(SELECT id FROM lessons WHERE slug=?) ORDER BY id DESC LIMIT 1', (code,LEGACY_LESSON)).fetchone()
                published=conn.execute('''SELECT w.share_token,w.share_active FROM published_works w
                    JOIN lessons l ON l.id=w.lesson_id WHERE w.code=? AND l.slug=?''',(code,LEGACY_LESSON)).fetchone()
            self.send_bytes(200, {'code': code, 'status': row['status'] if row else '未提交',
                'error': row['error'] if row else '', 'received_at': row['received_at'] if row else '',
                'url': share_url(published['share_token']) if published and published['share_active'] and published['share_token'] else None,
                'qr': qr_url(published['share_token']) if published and published['share_active'] and published['share_token'] else None})
        elif path.startswith('/api/works/') and path.endswith('/qr.png'):
            code = path.removeprefix('/api/works/').removesuffix('/qr.png')
            if not CODE_RE.fullmatch(code) or not ((WORKS/'current'/code).is_symlink() or (WORKS/'current'/code).is_dir()):
                return self.error(404, '作品尚未发布')
            with db() as conn:
                legacy = conn.execute('''SELECT legacy_allowed,share_active FROM published_works WHERE code=?
                    AND lesson_id=(SELECT id FROM lessons WHERE slug=?)''',(code,LEGACY_LESSON)).fetchone()
            if not legacy or not legacy['legacy_allowed'] or not legacy['share_active']: return self.error(404,'二维码不存在')
            try:
                import qrcode
                image = qrcode.make(work_url(code))
                out = io.BytesIO(); image.save(out, format='PNG')
                self.send_bytes(200, out.getvalue(), 'image/png')
            except ImportError:
                self.error(503, '二维码组件尚未安装')
        elif path.startswith('/preview/'):
            self.preview(path)
        elif path.startswith('/share/'):
            self.serve_shared(path)
        elif path.startswith('/gallery/'):
            self.serve_gallery(path)
        elif path.startswith('/collection/'):
            self.serve_collection(path)
        elif path.startswith('/works/') or path.startswith('/projects/'):
            self.serve_legacy(path)
        elif path == '/api/admin/roster.csv':
            if not self.admin(): return
            selected = parse_qs(urlsplit(self.path).query).get('class_id', [''])[0]
            if selected and not CLASS_RE.fullmatch(selected): return self.error(400, '班级编号格式不正确')
            with db() as conn:
                rows = conn.execute('SELECT class_id,code,upload_token FROM slots WHERE (?="" OR class_id=?) ORDER BY class_id,code', (selected,selected)).fetchall()
            out = io.StringIO(); writer = csv.writer(out)
            writer.writerow(['班级编号','学生账号','初始密码','学生姓名（老师填写）','家长联系方式（老师填写）'])
            for r in rows: writer.writerow([r['class_id'],r['code'],r['upload_token'],'',''])
            self.send_bytes(200, ('\ufeff'+out.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8',
                {'Content-Disposition': 'attachment; filename="classroom-roster.csv"'})
        elif STATIC_DIR:
            relative = path.lstrip('/')
            if not relative or path.endswith('/'):
                relative += 'index.html'
            self.static_file(STATIC_DIR, relative)
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

    def static_file(self, root, relative):
        relative = unquote(relative) or 'index.html'
        if relative.endswith('/'): relative += 'index.html'
        pure = PurePosixPath(relative)
        if pure.is_absolute() or '..' in pure.parts or any(part.startswith('.') for part in pure.parts):
            return self.error(404,'文件不存在')
        if not root.is_dir(): return self.error(404,'作品暂时不可用')
        target = root.joinpath(*pure.parts)
        if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
            return self.error(404,'文件不存在')
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        self.send_bytes(200,target.read_bytes(),mime + ('; charset=utf-8' if mime.startswith('text/') or mime in ('application/javascript','application/json','application/manifest+json') else ''))

    def shared_root(self, token):
        with db() as conn:
            course = conn.execute('''SELECT w.code,l.slug,l.format FROM published_works w
                JOIN lessons l ON l.id=w.lesson_id WHERE w.share_token=? AND w.share_active=1''',(token,)).fetchone()
            if course:
                return (WORKS/'current'/course['code'] if course['format']=='money'
                        else WORKS/'v2/current'/course['code']/course['slug'])
            free = conn.execute('SELECT code,id FROM independent_projects WHERE share_token=? AND share_active=1 AND published_submission_id IS NOT NULL',(token,)).fetchone()
        return WORKS/'free/current'/free['code']/str(free['id']) if free else None

    def serve_shared(self, path):
        match = re.fullmatch(r'/share/([A-Za-z0-9_-]{32,64})/(.*)',path)
        if not match: return self.error(404,'分享链接不存在')
        root = self.shared_root(match.group(1))
        if root is None: return self.error(404,'分享链接已失效')
        self.static_file(root,match.group(2))

    def serve_gallery(self,path):
        match=re.fullmatch(r'/gallery/([A-Za-z0-9_-]{32,64})/(.*)',path)
        if not match:return self.error(404,'公开作品不存在')
        token=match.group(1)
        with db() as conn:
            course=conn.execute('''SELECT w.code,l.slug,l.format FROM published_works w
                JOIN lessons l ON l.id=w.lesson_id WHERE w.share_token=? AND w.share_active=1 AND w.listed=1
                AND EXISTS(SELECT 1 FROM public_consents c WHERE c.code=w.code AND c.lesson_id=w.lesson_id
                AND c.submission_id=w.submission_id AND c.revoked_at='')''',(token,)).fetchone()
            free=conn.execute('''SELECT f.code,f.id FROM independent_projects f
                WHERE f.share_token=? AND f.share_active=1 AND f.listed=1
                AND EXISTS(SELECT 1 FROM public_consents c WHERE c.code=f.code AND c.independent_id=f.id
                AND c.submission_id=f.published_submission_id AND c.revoked_at='')''',(token,)).fetchone()
        if course:
            root=WORKS/'current'/course['code'] if course['format']=='money' else WORKS/'v2/current'/course['code']/course['slug']
        elif free:
            root=WORKS/'free/current'/free['code']/str(free['id'])
        else:return self.error(404,'公开作品已下架')
        self.static_file(root,match.group(2))

    def serve_collection(self,path):
        match=re.fullmatch(r'/collection/([A-Za-z0-9_-]{32,64})/',path)
        if not match:return self.error(404,'作品集不存在')
        with db() as conn:
            collection=conn.execute('''SELECT c.code,c.program_id,p.title,p.days FROM camp_collections c
                JOIN programs p ON p.id=c.program_id WHERE c.token=? AND c.active=1''',(match.group(1),)).fetchone()
            if not collection:return self.error(404,'作品集链接已失效')
            works=conn.execute('''SELECT l.title,l.day_no,w.share_token FROM lessons l
                JOIN published_works w ON w.lesson_id=l.id AND w.code=?
                WHERE l.program_id=? AND w.share_active=1 ORDER BY l.day_no,l.id''',
                (collection['code'],collection['program_id'])).fetchall()
        e=html.escape
        cards=''.join(f'<article class="card"><span class="eyebrow">第 {work["day_no"]} 天</span>'
                      f'<h2>{e(work["title"])}</h2><a class="button" href="{share_url(work["share_token"])}">打开这件作品</a></article>'
                      for work in works)
        if not cards:cards='<p class="muted">目前还没有通过老师审核的作品，请稍后再来看。</p>'
        page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>{e(collection['title'])}阶段作品集｜Code-X-Ai</title>
<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/site.css"></head><body class="site">
<header><a class="brand" href="/">✦ Code-X-Ai</a><nav><a href="/courses/">课程</a><a href="/consult/">联系老师</a></nav></header>
<main><div class="page-head"><span class="eyebrow">家长专属作品集 · {e(collection['code'])}</span><h1>{e(collection['title'])}</h1>
<p>孩子在 {collection['days']} 天课程中逐步完成的网页作品。这里仅收录老师已审核发布的版本，后续更新仍沿用各自的作品链接。</p></div>
<section class="section"><div class="course-list">{cards}</div></section>
<p class="muted">这条作品集链接可被持有者转发，请只发给需要查看的家人。作品里的个人记录仍留在使用它的手机浏览器。</p></main>
<footer><strong>Code-X-Ai · 儿童 AI 创作工作坊</strong></footer></body></html>'''
        self.send_bytes(200,page,'text/html; charset=utf-8',{'X-Robots-Tag':'noindex, nofollow, noarchive'})

    def serve_legacy(self,path):
        money = re.fullmatch(r'/works/([a-z][a-z0-9-]{2,30})/money/(.*)',path)
        project = re.fullmatch(r'/projects/([a-z][a-z0-9-]{2,30})/([a-z][a-z0-9-]{2,30})/(.*)',path)
        if not money and not project: return self.error(404,'旧作品地址不存在')
        code = (money or project).group(1)
        slug = LEGACY_LESSON if money else project.group(2)
        with db() as conn:
            row = conn.execute('''SELECT w.legacy_allowed,w.share_active,l.format FROM published_works w
                JOIN lessons l ON l.id=w.lesson_id WHERE w.code=? AND l.slug=?''',(code,slug)).fetchone()
        if not row or not row['legacy_allowed'] or not row['share_active']: return self.error(404,'旧作品地址已迁移')
        root = WORKS/'current'/code if row['format']=='money' else WORKS/'v2/current'/code/slug
        self.static_file(root,'money/'+money.group(2) if money else project.group(3))

    def share_qr(self,path):
        token = path.split('/')[3]
        if self.shared_root(token) is None: return self.error(404,'分享链接已失效')
        try:
            import qrcode
            image=qrcode.make(share_url(token)); out=io.BytesIO(); image.save(out,format='PNG')
            self.send_bytes(200,out.getvalue(),'image/png')
        except ImportError:
            self.error(503,'二维码组件尚未安装')

    def admin_independent(self):
        with db() as conn:
            rows = conn.execute('''SELECT f.*,s.id submission_id,s.status,s.error,s.received_at,s.preview_token,
                s.published_at FROM independent_projects f
                LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE independent_id=f.id)
                ORDER BY f.updated_at DESC,f.id DESC''').fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item['url']=share_url(item['share_token']) if item['share_token'] and item['share_active'] else None
            item['qr']=qr_url(item['share_token']) if item['url'] else None
            item['preview_url']='https://codexai.site/preview/'+item['preview_token']+'/' if item['status']=='待审核' else None
            result.append(item)
        self.send_bytes(200,result)

    def admin_collections(self):
        with db() as conn:
            rows=conn.execute('''SELECT c.code,c.program_id,c.token,c.active,c.created_at,c.updated_at,
                p.title program_title,p.days FROM camp_collections c JOIN programs p ON p.id=c.program_id
                ORDER BY c.updated_at DESC''').fetchall()
        self.send_bytes(200,[{key:row[key] for key in row.keys() if key!='token'}|
            {'url':collection_url(row['token']) if row['active'] else None} for row in rows])

    def admin_publication_events(self):
        with db() as conn:
            rows=conn.execute('''SELECT e.code,e.submission_id,e.action,e.created_at,
                COALESCE(l.title,f.title,'作品') title FROM publication_events e
                LEFT JOIN lessons l ON l.id=e.lesson_id
                LEFT JOIN independent_projects f ON f.id=e.independent_id
                ORDER BY e.id DESC LIMIT 20''').fetchall()
        self.send_bytes(200,[dict(row) for row in rows])

    def update_collection(self):
        body=self.read_json()
        code,program_id,active=body.get('code'),body.get('program_id'),body.get('active')
        if not isinstance(code,str) or not CODE_RE.fullmatch(code) or type(program_id) is not int or type(active) is not bool:
            return self.error(400,'作品集信息不正确')
        with db() as conn:
            enrolled=conn.execute('''SELECT 1 FROM enrollments e JOIN programs p ON p.id=e.program_id
                WHERE e.code=? AND e.program_id=? AND p.kind='camp' ''',(code,program_id)).fetchone()
            if not enrolled:return self.error(403,'这位学生尚未参加该创作营')
            current=conn.execute('SELECT token,active FROM camp_collections WHERE code=? AND program_id=?',
                                 (code,program_id)).fetchone()
            if not active and not current:return self.error(404,'作品集尚未创建')
            token=(current['token'] if current and current['active'] else secrets.token_urlsafe(32)) if active else current['token']
            created=now()
            conn.execute('''INSERT INTO camp_collections(code,program_id,token,active,created_at,updated_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(code,program_id) DO UPDATE SET
                token=excluded.token,active=excluded.active,updated_at=excluded.updated_at''',
                (code,program_id,token,int(active),created,created))
        self.send_bytes(200,{'url':collection_url(token) if active else None,'active':active})

    def admin_consents(self):
        with db() as conn:
            rows=conn.execute('SELECT * FROM public_consents ORDER BY id DESC LIMIT 300').fetchall()
        self.send_bytes(200,[dict(row) for row in rows])

    def admin_consultations(self):
        with db() as conn:
            cutoff=(datetime.now(timezone.utc)-timedelta(days=365)).isoformat(timespec='seconds')
            conn.execute('DELETE FROM consultations WHERE updated_at<?',(cutoff,))
            rows=conn.execute('''SELECT id,parent_name,contact_kind,contact,child_age,interest,message,
                source,entry_path,status,note,created_at,updated_at FROM consultations
                ORDER BY created_at DESC,id DESC LIMIT 500''').fetchall()
        self.send_bytes(200,[dict(row) for row in rows])

    def export_consultations(self):
        with db() as conn:
            cutoff=(datetime.now(timezone.utc)-timedelta(days=365)).isoformat(timespec='seconds')
            conn.execute('DELETE FROM consultations WHERE updated_at<?',(cutoff,))
            rows=conn.execute('''SELECT id,created_at,parent_name,contact_kind,contact,child_age,interest,
                message,source,status,note FROM consultations ORDER BY created_at DESC,id DESC''').fetchall()
        out=io.StringIO(); writer=csv.writer(out)
        writer.writerow(['编号','时间','家长称呼','联系渠道','联系方式','孩子年龄','感兴趣课程','留言','来源','状态','备注'])
        for row in rows:
            writer.writerow(["'"+str(value) if str(value).startswith(('=','+','-','@')) else value for value in row])
        self.send_bytes(200,('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8',
                        {'Content-Disposition':'attachment; filename="codexai-consultations.csv"'})

    def admin_versions(self):
        query=parse_qs(urlsplit(self.path).query)
        code=query.get('code',[''])[0]
        kind=query.get('kind',[''])[0]
        work_id=query.get('id',[''])[0]
        if not CODE_RE.fullmatch(code) or kind not in ('course','independent') or not work_id.isdecimal():
            return self.error(400,'作品信息不正确')
        field='lesson_id' if kind=='course' else 'independent_id'
        with db() as conn:
            rows=conn.execute(f'''SELECT id,status,error,received_at,published_at,preview_token
                FROM submissions WHERE code=? AND {field}=? ORDER BY id DESC''',(code,int(work_id))).fetchall()
        result=[]
        for row in rows:
            item=dict(row)
            item['preview_url']='https://codexai.site/preview/'+item['preview_token']+('/money/' if kind=='course' and self.lesson_format(int(work_id))=='money' else '/') if item['status'] in ('待审核','已发布') else None
            item.pop('preview_token')
            result.append(item)
        self.send_bytes(200,result)

    def lesson_format(self,lesson_id):
        with db() as conn:
            row=conn.execute('SELECT format FROM lessons WHERE id=?',(lesson_id,)).fetchone()
        return row['format'] if row else None

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
                w.url,w.listed,w.published_at,w.share_token,w.share_active,w.legacy_allowed
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
            data['url']=share_url(data['share_token']) if data['share_token'] and data['share_active'] else None
            data['qr']=qr_url(data['share_token']) if data['url'] else None
            data.pop('share_token')
            result.append(data)
        self.send_bytes(200,result)

    def student_dashboard(self, code):
        with db() as conn:
            rows = conn.execute('''SELECT p.id program_id,p.title program_title,p.kind,p.days,p.description,
                l.id lesson_id,l.slug lesson_slug,l.title lesson_title,l.day_no,l.format,l.starter_path,
                s.status,s.error,s.received_at,w.url,w.published_at,w.share_token,w.share_active,
                w.listed
                FROM enrollments e JOIN programs p ON p.id=e.program_id
                JOIN lessons l ON l.program_id=p.id
                LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE code=e.code AND lesson_id=l.id)
                LEFT JOIN published_works w ON w.code=e.code AND w.lesson_id=l.id
                WHERE e.code=? ORDER BY p.id DESC,l.day_no,l.id''',(code,)).fetchall()
            versions=conn.execute('''SELECT id,lesson_id,status,error,received_at,published_at
                FROM submissions WHERE code=? AND lesson_id IS NOT NULL ORDER BY id DESC''',(code,)).fetchall()
            collections=conn.execute('''SELECT program_id,token FROM camp_collections
                WHERE code=? AND active=1''',(code,)).fetchall()
        by_lesson={}
        for version in versions:
            by_lesson.setdefault(version['lesson_id'],[]).append(dict(version))
        result=[]
        for row in rows:
            data=dict(row); data['starter_available']=bool(data.pop('starter_path'))
            data['url']=share_url(data['share_token']) if data['share_token'] and data['share_active'] else None
            data['qr']=qr_url(data['share_token']) if data['url'] else None
            data['versions']=by_lesson.get(data['lesson_id'],[])
            data.pop('share_token'); result.append(data)
        self.send_bytes(200,{'code':code,'lessons':result,'collections':[
            {'program_id':row['program_id'],'url':collection_url(row['token'])} for row in collections]})

    def student_independent(self,code):
        with db() as conn:
            rows=conn.execute('''SELECT f.*,s.id submission_id,s.status,s.error,s.received_at,
                s.published_at FROM independent_projects f
                LEFT JOIN submissions s ON s.id=(SELECT MAX(id) FROM submissions WHERE independent_id=f.id)
                WHERE f.code=? ORDER BY f.updated_at DESC,f.id DESC''',(code,)).fetchall()
            versions=conn.execute('''SELECT id,independent_id,status,error,received_at,published_at
                FROM submissions WHERE code=? AND independent_id IS NOT NULL ORDER BY id DESC''',(code,)).fetchall()
        by_project={}
        for version in versions:
            by_project.setdefault(version['independent_id'],[]).append(dict(version))
        result=[]
        for row in rows:
            item=dict(row)
            item['url']=share_url(item['share_token']) if item['share_token'] and item['share_active'] else None
            item['qr']=qr_url(item['share_token']) if item['url'] else None
            item['versions']=by_project.get(item['id'],[])
            item.pop('share_token'); result.append(item)
        self.send_bytes(200,result)

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
            row = conn.execute('''SELECT w.url,w.legacy_allowed,w.share_active FROM published_works w JOIN lessons l ON l.id=w.lesson_id
                WHERE w.code=? AND l.slug=?''',match.groups()).fetchone()
        if not row or not row['legacy_allowed'] or not row['share_active']: return self.error(404,'旧二维码不存在')
        try:
            import qrcode
            image=qrcode.make(project_url(*match.groups())); output=io.BytesIO(); image.save(output,format='PNG')
            self.send_bytes(200,output.getvalue(),'image/png')
        except ImportError:
            self.error(503,'二维码组件尚未安装')

    def do_POST(self):
        path = urlsplit(self.path).path
        try:
            if path == '/api/public/consultations':
                self.create_consultation()
            elif re.fullmatch(r'/api/admin/consultations/\d+',path):
                if not self.admin(): return
                self.update_consultation(int(path.rsplit('/',1)[1]))
            elif re.fullmatch(r'/api/admin/consultations/\d+/delete',path):
                if not self.admin(): return
                self.delete_consultation(int(path.split('/')[4]))
            elif path == '/api/admin/classes':
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
            elif re.fullmatch(r'/api/admin/programs/\d+/marketing',path):
                if not self.admin(): return
                self.update_program_marketing(int(path.split('/')[4]))
            elif path == '/api/admin/site-content':
                if not self.admin(): return
                self.update_site_content()
            elif path == '/api/admin/wechat-qr':
                if not self.admin(): return
                self.upload_wechat_qr()
            elif path == '/api/admin/collections':
                if not self.admin(): return
                self.update_collection()
            elif path == '/api/admin/lessons':
                if not self.admin(): return
                self.create_lesson()
            elif path == '/api/admin/enroll-class':
                if not self.admin(): return
                self.enroll_class()
            elif path == '/api/admin/enroll-student':
                if not self.admin(): return
                self.enroll_student()
            elif re.fullmatch(r'/api/admin/lessons/\d+/starter',path):
                if not self.admin(): return
                self.upload_starter(path)
            elif re.fullmatch(r'/api/admin/visibility/[a-z][a-z0-9-]{2,30}/\d+',path):
                if not self.admin(): return
                self.visibility(path)
            elif path == '/api/admin/consents':
                if not self.admin(): return
                self.record_consent()
            elif re.fullmatch(r'/api/admin/consents/\d+/revoke',path):
                if not self.admin(): return
                self.revoke_consent(int(path.split('/')[4]))
            elif re.fullmatch(r'/api/admin/independent/\d+/visibility',path):
                if not self.admin(): return
                self.independent_visibility(int(path.split('/')[4]))
            elif re.fullmatch(r'/api/admin/(course|independent)/\d+/share',path):
                if not self.admin(): return
                self.rotate_share(path)
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
            elif path == '/api/student/independent':
                if not self.student_post_origin(): return
                code = self.student()
                if code: self.create_independent(code)
            elif re.fullmatch(r'/api/student/independent/\d+/submit',path):
                if not self.student_post_origin(): return
                code = self.student()
                if code: self.submit_independent(code,int(path.split('/')[4]))
            elif path.startswith('/api/submit/'):
                self.submit(path.removeprefix('/api/submit/'))
            elif path.startswith('/api/admin/publish/'):
                if not self.admin(): return
                self.publish(path.removeprefix('/api/admin/publish/'))
            elif path.startswith('/api/admin/rollback/'):
                if not self.admin(): return
                self.rollback(path.removeprefix('/api/admin/rollback/'))
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

    def update_program_marketing(self,program_id):
        body=self.read_json(limit=8192)
        status=body.get('status')
        fields={name:str(body.get(name,'')).strip() for name in
                ('summary','audience','outcome','duration','parent_role')}
        if status not in ('draft','consulting','paused','archived') or any(len(value)>500 for value in fields.values()):
            return self.error(400,'课程公开信息不正确')
        if status=='consulting' and any(len(value)<5 for value in fields.values()):
            return self.error(400,'开放咨询前请填写简介、适龄、成果、时长和家长参与方式')
        with db() as conn:
            program=conn.execute('SELECT id FROM programs WHERE id=?',(program_id,)).fetchone()
            if not program:return self.error(404,'课程不存在')
            if status=='consulting' and not conn.execute('SELECT 1 FROM lessons WHERE program_id=?',(program_id,)).fetchone():
                return self.error(409,'请先为这门课程添加至少一个课题')
            conn.execute('''UPDATE programs SET marketing_status=?,marketing_summary=?,marketing_audience=?,
                marketing_outcome=?,marketing_duration=?,marketing_parent_role=? WHERE id=?''',
                (status,fields['summary'],fields['audience'],fields['outcome'],fields['duration'],
                 fields['parent_role'],program_id))
        self.send_bytes(200,{'id':program_id,'status':status})

    def site_content(self):
        with db() as conn:
            settings={row['name']:row['value'] for row in conn.execute('SELECT name,value FROM site_settings')}
        self.send_bytes(200,{'teacher_intro':settings.get('teacher_intro',''),
            'demo_title':settings.get('demo_title','零花钱计划师'),
            'demo_summary':settings.get('demo_summary',''),
            'faqs':json.loads(settings.get('faqs','[]')),
            'wechat_qr_available':(DATA/'site/wechat-qr.png').is_file()})

    def update_site_content(self):
        body=self.read_json(limit=25000)
        intro=body.get('teacher_intro')
        title=body.get('demo_title')
        summary=body.get('demo_summary')
        faqs=body.get('faqs')
        if (not isinstance(intro,str) or len(intro.strip())>600 or not isinstance(title,str) or
            not 2<=len(title.strip())<=80 or not isinstance(summary,str) or
            not 5<=len(summary.strip())<=300 or not isinstance(faqs,list) or not 1<=len(faqs)<=20):
            return self.error(400,'网站内容不完整或过长')
        clean=[]
        for item in faqs:
            if not isinstance(item,dict) or not isinstance(item.get('q'),str) or not isinstance(item.get('a'),str):
                return self.error(400,'常见问题格式不正确')
            q,a=item['q'].strip(),item['a'].strip()
            if not 3<=len(q)<=160 or not 5<=len(a)<=600:return self.error(400,'常见问题长度不正确')
            clean.append({'q':q,'a':a})
        values={'teacher_intro':intro.strip(),'demo_title':title.strip(),'demo_summary':summary.strip(),
                'faqs':json.dumps(clean,ensure_ascii=False)}
        with db() as conn:
            for name,value in values.items():
                conn.execute('''INSERT INTO site_settings(name,value,updated_at) VALUES (?,?,?)
                    ON CONFLICT(name) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at''',
                    (name,value,now()))
        self.send_bytes(200,{'saved':True})

    def public_wechat_qr(self):
        image=DATA/'site/wechat-qr.png'
        if not image.is_file():return self.error(404,'微信二维码尚未上传')
        self.send_bytes(200,image.read_bytes(),'image/png')

    def upload_wechat_qr(self):
        if self.headers.get('Content-Type','').split(';')[0] not in ('image/png','image/jpeg'):
            return self.error(415,'请上传 PNG 或 JPEG 图片')
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:length=0
        if not 1<=length<=2_000_000:return self.error(413,'二维码图片不能超过 2MB')
        body=self.rfile.read(length)
        if len(body)!=length:return self.error(400,'图片上传中断')
        try:
            from PIL import Image,UnidentifiedImageError
            with Image.open(io.BytesIO(body)) as source:
                source.verify()
            with Image.open(io.BytesIO(body)) as source:
                if source.width>4000 or source.height>4000 or source.width<100 or source.height<100:
                    return self.error(400,'二维码图片尺寸须在 100–4000 像素之间')
                image=source.convert('RGB')
                with tempfile.NamedTemporaryFile(dir=DATA/'site',suffix='.png',delete=False) as output:
                    scratch=Path(output.name)
                try:
                    image.save(scratch,format='PNG')
                    os.replace(scratch,DATA/'site/wechat-qr.png')
                finally:scratch.unlink(missing_ok=True)
        except (UnidentifiedImageError,OSError,ValueError):
            return self.error(400,'图片无法识别，请换一张清晰的二维码')
        self.send_bytes(200,{'uploaded':True})

    def public_courses(self):
        with db() as conn:
            rows=conn.execute('''SELECT slug,title,kind,days,marketing_summary summary,
                marketing_audience audience,marketing_outcome outcome,marketing_duration duration
                FROM programs WHERE marketing_status='consulting' ORDER BY id''').fetchall()
        self.send_bytes(200,[dict(row)|{'url':f'https://codexai.site/courses/{"money" if row["slug"]==LEGACY_PROGRAM else row["slug"]}/'} for row in rows])

    def public_course_page(self,slug):
        if slug=='money':slug=LEGACY_PROGRAM
        with db() as conn:
            program=conn.execute('''SELECT * FROM programs WHERE slug=? AND marketing_status IN ('consulting','paused')''',
                                 (slug,)).fetchone()
            if not program:return self.error(404,'课程尚未公开')
            lessons=conn.execute('SELECT day_no,title FROM lessons WHERE program_id=? ORDER BY day_no,id',
                                 (program['id'],)).fetchall()
        e=html.escape
        title=e(program['title']);description=e(program['marketing_summary'])
        label='开放咨询' if program['marketing_status']=='consulting' else '暂停咨询'
        day_list=''.join(f'<li>第 {lesson["day_no"]} 天 · {e(lesson["title"])}</li>' for lesson in lessons)
        if program['marketing_status']=='consulting':
            action=f'<a class="button" href="/consult/?course={e(slug)}" data-track-consult>咨询这门课程</a>'
        else:
            action='<p class="notice">这门课程目前暂停咨询，开放时间请关注课程列表。</p>'
        page=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}｜Code-X-Ai 儿童 AI 创作工作坊</title><meta name="description" content="{description[:150]}">
<link rel="canonical" href="https://codexai.site/courses/{e(slug)}/"><link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/site.css"><script src="/site.js" defer></script></head>
<body class="site"><header><a class="brand" href="/">✦ Code-X-Ai</a><nav aria-label="主导航"><a href="/courses/">课程与创作营</a><a href="/showcase/">孩子作品</a><a href="/method/">怎么上课</a><a href="/about/">关于我</a><a href="/faq/">常见问题</a><a class="nav-cta" href="/consult/" data-track-consult>咨询课程</a><a class="nav-login" href="https://www.codexai.site/student/">学生登录</a></nav></header>
<main><div class="breadcrumb"><a href="/">首页</a> / <a href="/courses/">课程与创作营</a> / {title}</div>
<section class="page-head"><span class="eyebrow">{label} · {e(program['kind'])}</span><h1>{title}</h1><p>{description}</p>{action}</section>
<section class="section"><div class="facts"><div class="fact"><strong>{e(program['marketing_audience'])}</strong><span>适合谁</span></div><div class="fact"><strong>{e(program['marketing_duration'])}</strong><span>课程时长</span></div><div class="fact"><strong>{e(program['marketing_outcome'])}</strong><span>孩子带走的作品</span></div></div></section>
<section class="section"><span class="eyebrow">课程安排</span><h2>孩子会经历什么？</h2><p>{description}</p><ul>{day_list}</ul><p>家长参与：{e(program['marketing_parent_role'])}</p></section>
<section class="section"><div class="cta-panel"><div><h2>有问题想先问老师？</h2><p>具体排期和费用请在咨询时了解。</p></div>{action}</div></section></main>
<footer><div><strong>Code-X-Ai · 儿童 AI 创作工作坊</strong></div><div><a href="/consult/">咨询方式</a><a href="/privacy/">隐私说明</a><a href="https://www.codexai.site/teacher/">教师登录</a></div></footer></body></html>'''
        self.send_bytes(200,page,'text/html; charset=utf-8',{'X-Robots-Tag':'index, follow' if program['marketing_status']=='consulting' else 'noindex, nofollow'})

    def public_sitemap(self):
        with db() as conn:
            slugs=[row['slug'] for row in conn.execute("SELECT slug FROM programs WHERE marketing_status='consulting'")]
            works=[gallery_url(row['share_token']) for row in conn.execute('''SELECT w.share_token FROM published_works w WHERE w.listed=1 AND w.share_active=1
                AND EXISTS(SELECT 1 FROM public_consents c WHERE c.code=w.code AND c.lesson_id=w.lesson_id
                AND c.submission_id=w.submission_id AND c.revoked_at='')''')]
            works += [gallery_url(row['share_token']) for row in conn.execute('''SELECT f.share_token FROM independent_projects f
                WHERE f.listed=1 AND f.share_active=1 AND EXISTS(SELECT 1 FROM public_consents c
                WHERE c.code=f.code AND c.independent_id=f.id AND c.submission_id=f.published_submission_id
                AND c.revoked_at='')''')]
        pages=['/','/courses/','/showcase/','/method/','/about/','/faq/','/consult/','/privacy/']
        pages += [f'/courses/{"money" if slug==LEGACY_PROGRAM else slug}/' for slug in slugs]
        pages += [url.removeprefix('https://codexai.site') for url in works]
        body='<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        body+=''.join('<url><loc>'+xml_escape('https://codexai.site'+path)+'</loc></url>' for path in pages)
        body+='</urlset>'
        self.send_bytes(200,body,'application/xml; charset=utf-8')

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

    def enroll_student(self):
        body=self.read_json()
        code,program_id=body.get('code'),body.get('program_id')
        if not isinstance(code,str) or not CODE_RE.fullmatch(code) or type(program_id) is not int:
            return self.error(400,'学生编号或课程信息不正确')
        with db() as conn:
            if not conn.execute('SELECT 1 FROM slots WHERE code=?',(code,)).fetchone():
                return self.error(404,'学生编号不存在')
            if not conn.execute('SELECT 1 FROM programs WHERE id=?',(program_id,)).fetchone():
                return self.error(404,'课程不存在')
            conn.execute('INSERT OR IGNORE INTO enrollments(code,program_id) VALUES (?,?)',(code,program_id))
        self.send_bytes(200,{'enrolled':code})

    def visibility(self,path):
        match=re.fullmatch(r'/api/admin/visibility/([a-z][a-z0-9-]{2,30})/(\d+)',path)
        body=self.read_json()
        if type(body.get('listed')) is not bool: return self.error(400,'请选择是否在作品展显示')
        code,lesson_id=match.group(1),int(match.group(2))
        with db() as conn:
            if body['listed'] and not conn.execute('''SELECT 1 FROM published_works WHERE code=? AND lesson_id=?
                AND share_active=1 AND share_token IS NOT NULL''',(code,lesson_id)).fetchone():
                return self.error(409,'请先启用家长分享链接')
            if body['listed'] and not conn.execute('''SELECT 1 FROM public_consents c
                JOIN published_works w ON w.code=c.code AND w.lesson_id=c.lesson_id
                WHERE c.code=? AND c.lesson_id=? AND c.submission_id=w.submission_id
                AND c.revoked_at='' LIMIT 1''',(code,lesson_id)).fetchone():
                return self.error(409,'请先登记这件作品的家长公开展示同意')
            cur=conn.execute('UPDATE published_works SET listed=? WHERE code=? AND lesson_id=?',
                             (int(body['listed']),code,lesson_id))
            if cur.rowcount!=1: return self.error(404,'已发布作品不存在')
        self.send_bytes(200,{'listed':body['listed']})

    def independent_visibility(self,project_id):
        body=self.read_json()
        if type(body.get('listed')) is not bool: return self.error(400,'请选择是否在作品展显示')
        with db() as conn:
            project=conn.execute('SELECT code,published_submission_id,share_active,share_token FROM independent_projects WHERE id=?',(project_id,)).fetchone()
            if not project or not project['published_submission_id']: return self.error(404,'已发布作品不存在')
            if body['listed'] and (not project['share_active'] or not project['share_token']):
                return self.error(409,'请先启用家长分享链接')
            if body['listed'] and not conn.execute('''SELECT 1 FROM public_consents WHERE code=? AND independent_id=?
                AND submission_id=? AND revoked_at='' LIMIT 1''',
                (project['code'],project_id,project['published_submission_id'])).fetchone():
                return self.error(409,'请先登记这件作品的家长公开展示同意')
            conn.execute('UPDATE independent_projects SET listed=? WHERE id=?',(int(body['listed']),project_id))
        self.send_bytes(200,{'listed':body['listed']})

    def record_consent(self):
        body=self.read_json()
        code,lesson_id,project_id=body.get('code'),body.get('lesson_id'),body.get('independent_id')
        guardian_ref=str(body.get('guardian_ref','')).strip()
        channel=str(body.get('channel','')).strip()
        consent_at=str(body.get('consent_at','')).strip()
        evidence_ref=str(body.get('evidence_ref','')).strip()
        if (not isinstance(code,str) or not CODE_RE.fullmatch(code) or
            (type(lesson_id) is int)==(type(project_id) is int) or
            not 2<=len(guardian_ref)<=80 or not 2<=len(channel)<=40 or
            not re.fullmatch(r'\d{4}-\d{2}-\d{2}',consent_at) or
            not 2<=len(evidence_ref)<=200):
            return self.error(400,'请填完整的作品、家长确认人、同意日期、渠道和凭据位置')
        with db() as conn:
            if lesson_id is not None:
                exists=conn.execute('SELECT submission_id FROM published_works WHERE code=? AND lesson_id=?',(code,lesson_id)).fetchone()
            else:
                exists=conn.execute('SELECT published_submission_id submission_id FROM independent_projects WHERE code=? AND id=? AND published_submission_id IS NOT NULL',(code,project_id)).fetchone()
            if not exists:return self.error(404,'作品尚未发布')
            cur=conn.execute('''INSERT INTO public_consents
                (code,lesson_id,independent_id,submission_id,guardian_ref,channel,consent_at,evidence_ref,recorded_at)
                VALUES (?,?,?,?,?,?,?,?,?)''',(code,lesson_id,project_id,exists['submission_id'],guardian_ref,channel,consent_at,evidence_ref,now()))
        self.send_bytes(201,{'id':cur.lastrowid,'recorded':True})

    def revoke_consent(self,consent_id):
        with db() as conn:
            row=conn.execute("SELECT * FROM public_consents WHERE id=? AND revoked_at=''",(consent_id,)).fetchone()
            if not row:return self.error(404,'有效同意记录不存在')
            conn.execute('UPDATE public_consents SET revoked_at=? WHERE id=?',(now(),consent_id))
            if row['lesson_id'] is not None:
                conn.execute('UPDATE published_works SET listed=0 WHERE code=? AND lesson_id=?',(row['code'],row['lesson_id']))
            else:
                conn.execute('UPDATE independent_projects SET listed=0 WHERE code=? AND id=?',(row['code'],row['independent_id']))
        self.send_bytes(200,{'revoked':True})

    def rotate_share(self,path):
        match=re.fullmatch(r'/api/admin/(course|independent)/(\d+)/share',path)
        kind,work_id=match.group(1),int(match.group(2))
        body=self.read_json()
        if type(body.get('active')) is not bool:return self.error(400,'请选择启用或撤销分享')
        token=secrets.token_urlsafe(32) if body['active'] else None
        with db() as conn:
            if kind=='course':
                code=body.get('code')
                if not isinstance(code,str) or not CODE_RE.fullmatch(code):return self.error(400,'学生编号不正确')
                cur=conn.execute('''UPDATE published_works SET share_token=?,share_active=?,url=?,legacy_allowed=0,
                    listed=CASE WHEN ?=1 THEN listed ELSE 0 END WHERE code=? AND lesson_id=?''',
                    (token,int(body['active']),share_url(token) if token else '',int(body['active']),code,work_id))
            else:
                cur=conn.execute('''UPDATE independent_projects SET share_token=?,share_active=?,listed=CASE WHEN ?=1 THEN listed ELSE 0 END
                    WHERE id=? AND published_submission_id IS NOT NULL''',(token,int(body['active']),int(body['active']),work_id))
            if cur.rowcount!=1:return self.error(404,'已发布作品不存在')
        self.send_bytes(200,{'active':body['active'],'url':share_url(token) if token else None,'qr':qr_url(token) if token else None})

    def create_independent(self,code):
        body=self.read_json()
        title,summary,category=(str(body.get(key,'')).strip() for key in ('title','summary','category'))
        if not 2<=len(title)<=60 or not 5<=len(summary)<=300 or not 2<=len(category)<=30:
            return self.error(400,'请填写作品名称、想解决的问题和作品类别')
        with db() as conn:
            cur=conn.execute('''INSERT INTO independent_projects
                (code,title,summary,category,created_at,updated_at) VALUES (?,?,?,?,?,?)''',
                (code,title,summary,category,now(),now()))
        self.send_bytes(201,{'id':cur.lastrowid,'title':title})

    def create_consultation(self):
        if self.headers.get('Origin')!='https://codexai.site':
            return self.error(403,'请从课程网站提交咨询')
        body=self.read_json()
        if str(body.get('company','')).strip():
            return self.send_bytes(201,{'ok':True})
        name=str(body.get('parent_name','')).strip()
        kind=body.get('contact_kind')
        contact=str(body.get('contact','')).strip()
        age=str(body.get('child_age','')).strip()
        interest=str(body.get('interest','')).strip()
        message=str(body.get('message','')).strip()
        source=str(body.get('source','')).strip()
        entry=str(body.get('entry_path','')).strip()
        if (body.get('consent') is not True or not 1<=len(name)<=40 or kind not in ('微信','手机') or
            not 4<=len(contact)<=80 or not 1<=len(age)<=20 or not 2<=len(interest)<=60 or
            len(message)>500 or len(source)>80 or len(entry)>200 or not entry.startswith('/')):
            return self.error(400,'请填写家长称呼、联系方式、孩子年龄和感兴趣的课程，并确认隐私说明')
        remote=self.headers.get('X-Forwarded-For','').split(',')[0].strip() or self.client_address[0]
        ip_hash=hashlib.sha256((ADMIN_TOKEN+remote).encode()).hexdigest()
        cutoff=(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(timespec='seconds')
        created=now()
        with db() as conn:
            retention=(datetime.now(timezone.utc)-timedelta(days=365)).isoformat(timespec='seconds')
            conn.execute('DELETE FROM consultations WHERE updated_at<?',(retention,))
            count=conn.execute('SELECT COUNT(*) FROM consultations WHERE ip_hash=? AND created_at>=?',
                               (ip_hash,cutoff)).fetchone()[0]
            if count>=8:return self.error(429,'提交较频繁，请稍后再试或直接添加微信咨询')
            duplicate=conn.execute('SELECT 1 FROM consultations WHERE contact=? AND created_at>=?',
                                   (contact,cutoff)).fetchone()
            if not duplicate:
                conn.execute('''INSERT INTO consultations
                    (parent_name,contact_kind,contact,child_age,interest,message,source,entry_path,ip_hash,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                    (name,kind,contact,age,interest,message,source,entry,ip_hash,created,created))
        self.send_bytes(201,{'ok':True,'message':'已收到咨询，老师会用你留下的方式联系你'})

    def update_consultation(self,consultation_id):
        body=self.read_json()
        status=body.get('status')
        note=str(body.get('note','')).strip()
        if status not in ('新咨询','已联系','已约体验','已报名','暂不跟进') or len(note)>500:
            return self.error(400,'请选择有效状态，备注不能超过500字')
        with db() as conn:
            cur=conn.execute('UPDATE consultations SET status=?,note=?,updated_at=? WHERE id=?',
                             (status,note,now(),consultation_id))
            if cur.rowcount!=1:return self.error(404,'咨询记录不存在')
        self.send_bytes(200,{'id':consultation_id,'status':status})

    def delete_consultation(self,consultation_id):
        with db() as conn:
            cur=conn.execute('DELETE FROM consultations WHERE id=?',(consultation_id,))
            if cur.rowcount!=1:return self.error(404,'咨询记录不存在')
        self.send_bytes(200,{'deleted':True})

    def submit_independent(self,code,project_id):
        with db() as conn:
            project=conn.execute('SELECT id,title FROM independent_projects WHERE id=? AND code=?',(project_id,code)).fetchone()
        if not project:return self.error(404,'作品不存在')
        self.submit(code,authenticated=True,independent_id=project_id,independent_title=project['title'])

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
                                   '--title',lesson['title']],capture_output=True,text=True,encoding='utf-8',
                                  errors='replace',timeout=30)
            if result.returncode:
                return self.error(422,'起始包检查未通过：'+(result.stderr or result.stdout).strip()[-250:])
            target=DATA/'starters'/f'{lesson_id}.zip'
            shutil.copy2(archive,target)
            with db() as conn: conn.execute('UPDATE lessons SET starter_path=? WHERE id=?',(str(target),lesson_id))
        self.send_bytes(200,{'lesson_id':lesson_id,'starter_available':True})

    def submit(self, code, lesson_id=None, authenticated=False,independent_id=None,independent_title=None):
        if not authenticated and not self.code_and_token(code): return
        if lesson_id is None and independent_id is None:
            with db() as conn:
                lesson_id=conn.execute('SELECT id FROM lessons WHERE slug=?',(LEGACY_LESSON,)).fetchone()['id']
        lesson=self.student_lesson(code,lesson_id) if independent_id is None else None
        if independent_id is None and not lesson: return self.error(403,'这个课题尚未分配给你')
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
                cur = conn.execute('''INSERT INTO submissions
                    (code,received_at,status,preview_token,lesson_id,independent_id) VALUES (?,?,?,?,?,?)''',
                    (code,now(),'检查中',secrets.token_urlsafe(32),lesson_id,independent_id))
                sid = cur.lastrowid
                if independent_id is not None:
                    conn.execute('UPDATE independent_projects SET updated_at=? WHERE id=?',(now(),independent_id))
            archive_dir = DATA/'archives'/code
            archive_dir.mkdir(exist_ok=True)
            shutil.copy2(archive,archive_dir/f'{sid}.zip')
            try:
                commands = ([sys.executable,str(BASE/'unpack-student-zip.py'),str(archive),str(temp/'unpacked')],
                            [sys.executable,str(BASE/'package-student.py'),str(temp/'unpacked'),code,'--output',str(temp/'packages')]) \
                           if lesson and lesson['format']=='money' else ([sys.executable,str(BASE/'prepare-web-zip.py'),
                            str(archive),str(temp/'packages'/code),'--title',independent_title or lesson['title']],)
                for command in commands:
                    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=30)
                    if result.returncode:
                        raise ValueError((result.stderr or result.stdout).strip()[-300:])
                shutil.move(str(temp/'packages'/code), DATA/'prepared'/str(sid))
                with db() as conn: conn.execute('UPDATE submissions SET status=? WHERE id=?',('待审核',sid))
                self.send_bytes(201, {'id':sid,'code':code,'lesson_id':lesson_id,'independent_id':independent_id,
                    'status':'待审核','message':'上传成功，正在等待老师检查和发布'})
            except (ValueError, subprocess.TimeoutExpired) as exc:
                message = str(exc).replace('\n',' ')[:300]
                with db() as conn: conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',message,sid))
                self.error(422, '文件检查未通过：'+message)

    def publish(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        with db() as conn:
            row = conn.execute('''SELECT s.*,l.format,l.slug,l.title,f.title independent_title FROM submissions s
                LEFT JOIN lessons l ON l.id=s.lesson_id
                LEFT JOIN independent_projects f ON f.id=s.independent_id WHERE s.id=?''',(int(id_text),)).fetchone()
            if not row: return self.error(404,'提交不存在')
            if row['independent_id'] is not None:
                latest=conn.execute('SELECT MAX(id) FROM submissions WHERE independent_id=?',
                                    (row['independent_id'],)).fetchone()[0]
            else:
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
        elif row['independent_id'] is not None:
            target = WORKS/'free/releases'/code/str(row['independent_id'])/release
            link = WORKS/'free/current'/code/str(row['independent_id'])
            link_target = Path('../../releases')/code/str(row['independent_id'])/release
        else:
            target = WORKS/'v2/releases'/code/row['slug']/release
            link = WORKS/'v2/current'/code/row['slug']
            link_target = Path('../../releases')/code/row['slug']/release
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        if row['format']!='money': os.chmod(target.parent.parent,0o755)
        os.chmod(target.parent,0o755)
        shutil.copytree(src,target)
        os.chmod(target,0o755)
        for item in target.rglob('*'):
            os.chmod(item,0o755 if item.is_dir() else 0o644)
        link.parent.mkdir(exist_ok=True,mode=0o755)
        os.chmod(link.parent,0o755)
        activate_release(link,link_target,target)
        published_at=now()
        with db() as conn:
            conn.execute('UPDATE submissions SET status=?,published_at=? WHERE id=?',('已发布',published_at,row['id']))
            if row['independent_id'] is not None:
                current=conn.execute('SELECT share_token,share_active,published_submission_id FROM independent_projects WHERE id=?',
                                     (row['independent_id'],)).fetchone()
                active=bool(current['share_active']) if current['published_submission_id'] else True
                token=(current['share_token'] or secrets.token_urlsafe(32)) if active else None
                conn.execute('''UPDATE independent_projects SET published_submission_id=?,share_token=?,
                    share_active=?,listed=0,updated_at=? WHERE id=?''',(row['id'],token,int(active),published_at,row['independent_id']))
            else:
                current=conn.execute('SELECT share_token,share_active FROM published_works WHERE code=? AND lesson_id=?',
                                     (code,row['lesson_id'])).fetchone()
                active=bool(current['share_active']) if current else True
                token=(current['share_token'] if current and current['share_token'] else secrets.token_urlsafe(32)) if active else None
                conn.execute('''INSERT INTO published_works
                    (code,lesson_id,submission_id,url,listed,published_at,share_token,share_active,legacy_allowed)
                    VALUES (?,?,?,?,0,?,?,?,0) ON CONFLICT(code,lesson_id) DO UPDATE SET
                    submission_id=excluded.submission_id,url=excluded.url,published_at=excluded.published_at,
                    listed=0,
                    share_token=excluded.share_token,share_active=excluded.share_active''',
                    (code,row['lesson_id'],row['id'],share_url(token) if token else '',published_at,token,int(active)))
            conn.execute('''INSERT INTO publication_events(code,lesson_id,independent_id,submission_id,action,created_at)
                VALUES (?,?,?,?,?,?)''',(code,row['lesson_id'],row['independent_id'],row['id'],'发布',published_at))
        self.send_bytes(200,{'code':code,'lesson_id':row['lesson_id'],'independent_id':row['independent_id'],
            'status':'已发布','url':share_url(token) if token else None,'qr':qr_url(token) if token else None})

    def rollback(self,id_text):
        if not id_text.isdecimal():return self.error(400,'版本编号不正确')
        with db() as conn:
            row=conn.execute('''SELECT s.*,l.format,l.slug FROM submissions s
                LEFT JOIN lessons l ON l.id=s.lesson_id WHERE s.id=?''',(int(id_text),)).fetchone()
            if not row or row['status']!='已发布':return self.error(404,'只能回退到此前已发布的版本')
            if row['independent_id'] is not None:
                published=conn.execute('SELECT share_token,share_active FROM independent_projects WHERE id=? AND code=? AND published_submission_id IS NOT NULL',
                                       (row['independent_id'],row['code'])).fetchone()
            else:
                published=conn.execute('SELECT share_token,share_active FROM published_works WHERE lesson_id=? AND code=?',
                                       (row['lesson_id'],row['code'])).fetchone()
            if not published:return self.error(404,'当前作品不存在')
        src=DATA/'prepared'/id_text
        required=src/'money/index.html' if row['format']=='money' else src/'index.html'
        if not required.is_file():return self.error(409,'这个版本的文件已缺失，无法回退')
        code=row['code']
        release=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-rollback-'+id_text+'-'+secrets.token_hex(3)
        if row['format']=='money':
            target=WORKS/'releases'/code/release;link=WORKS/'current'/code
            link_target=Path('../releases')/code/release
        elif row['independent_id'] is not None:
            target=WORKS/'free/releases'/code/str(row['independent_id'])/release
            link=WORKS/'free/current'/code/str(row['independent_id'])
            link_target=Path('../../releases')/code/str(row['independent_id'])/release
        else:
            target=WORKS/'v2/releases'/code/row['slug']/release
            link=WORKS/'v2/current'/code/row['slug']
            link_target=Path('../../releases')/code/row['slug']/release
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        os.chmod(target.parent,0o755)
        if row['format']!='money':os.chmod(target.parent.parent,0o755)
        shutil.copytree(src,target)
        os.chmod(target,0o755)
        for item in target.rglob('*'):
            os.chmod(item,0o755 if item.is_dir() else 0o644)
        link.parent.mkdir(exist_ok=True,mode=0o755)
        os.chmod(link.parent,0o755)
        activate_release(link,link_target,target)
        changed=now()
        with db() as conn:
            if row['independent_id'] is not None:
                conn.execute('''UPDATE independent_projects SET published_submission_id=?,listed=0,updated_at=?
                    WHERE id=?''',(row['id'],changed,row['independent_id']))
            else:
                conn.execute('''UPDATE published_works SET submission_id=?,listed=0,published_at=?
                    WHERE code=? AND lesson_id=?''',(row['id'],changed,code,row['lesson_id']))
            conn.execute('''INSERT INTO publication_events(code,lesson_id,independent_id,submission_id,action,created_at)
                VALUES (?,?,?,?,?,?)''',(code,row['lesson_id'],row['independent_id'],row['id'],'回退',changed))
        token=published['share_token'] if published['share_active'] else None
        self.send_bytes(200,{'rolled_back_to':row['id'],'url':share_url(token) if token else None})

    def reject(self, id_text):
        if not id_text.isdecimal(): return self.error(400,'提交编号不正确')
        body = self.read_json()
        reason = str(body.get('reason','')).strip()[:200]
        if not reason: return self.error(400,'请填写需要修改的原因')
        with db() as conn:
            row = conn.execute('SELECT code,lesson_id,independent_id,status FROM submissions WHERE id=?',(int(id_text),)).fetchone()
            if not row or row['status'] != '待审核': return self.error(409,'这个提交无法退回')
            if row['independent_id'] is not None:
                latest=conn.execute('SELECT MAX(id) FROM submissions WHERE independent_id=?',
                                    (row['independent_id'],)).fetchone()[0]
            else:
                latest=conn.execute('SELECT MAX(id) FROM submissions WHERE code=? AND lesson_id=?',
                                    (row['code'],row['lesson_id'])).fetchone()[0]
            if latest != int(id_text):
                return self.error(409,'已有更新的提交')
            conn.execute('UPDATE submissions SET status=?,error=? WHERE id=?',('需修改',reason,int(id_text)))
        self.send_bytes(200,{'status':'需修改'})


if __name__ == '__main__':
    init()
    host = os.environ.get('CODEXAI_BIND','127.0.0.1')
    port = int(os.environ.get('CODEXAI_PORT','8766'))
    ThreadingHTTPServer((host,port),Handler).serve_forever()
