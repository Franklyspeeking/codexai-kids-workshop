#!/usr/bin/env python3
"""Create a safe local classroom dataset and run the management site on Windows."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import os
from pathlib import Path
import secrets
from http.server import ThreadingHTTPServer
import webbrowser


ROOT = Path(__file__).resolve().parent.parent
PREPARATION = ROOT / 'preparation'
LOCAL_ROOT = ROOT / 'output' / 'local-classroom'
TOKEN_FILE = PREPARATION / '.teacher-admin-token'
TEACHER_FILE = PREPARATION / '本地教师账号.txt'
ROSTER_FILE = PREPARATION / '本地演示学生账号.csv'
MIN_ADMIN_PASSWORD_LENGTH = 7


def admin_token() -> str:
    if TOKEN_FILE.is_file():
        token = TOKEN_FILE.read_text(encoding='utf-8').strip()
        if len(token) >= MIN_ADMIN_PASSWORD_LENGTH:
            return token
    PREPARATION.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    TOKEN_FILE.write_text(token + '\n', encoding='utf-8')
    return token


def load_service(token: str, port: int):
    os.environ['CODEXAI_ADMIN_TOKEN'] = token
    os.environ['CODEXAI_DATA_DIR'] = str(LOCAL_ROOT / 'data')
    os.environ['CODEXAI_WORKS_DIR'] = str(LOCAL_ROOT / 'works')
    os.environ['CODEXAI_STATIC_DIR'] = str(ROOT / 'codexai-site' / 'dist')
    os.environ['CODEXAI_PUBLIC_ORIGIN'] = f'http://127.0.0.1:{port}'
    spec = importlib.util.spec_from_file_location('codexai_upload_service', ROOT / 'scripts' / 'upload-service.py')
    service = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(service)
    service.init()
    return service


def seed_demo(service, count: int) -> list[dict[str, str]]:
    class_id = 'demo'
    with service.db() as conn:
        existing = conn.execute('SELECT code,class_id,upload_token FROM slots WHERE class_id=? ORDER BY code',
                                (class_id,)).fetchall()
        if not existing:
            created_at = service.now()
            rows = [(f'{class_id}-s{number:02d}', class_id, secrets.token_urlsafe(9), created_at)
                    for number in range(1, count + 1)]
            conn.executemany('INSERT INTO slots(code,class_id,upload_token,created_at) VALUES (?,?,?,?)', rows)
        programs = [row['id'] for row in conn.execute('SELECT id FROM programs ORDER BY id')]
        codes = [row['code'] for row in conn.execute('SELECT code FROM slots WHERE class_id=? ORDER BY code',
                                                     (class_id,))]
        conn.executemany('INSERT OR IGNORE INTO enrollments(code,program_id) VALUES (?,?)',
                         [(code, program_id) for code in codes for program_id in programs])
        accounts = [dict(row) for row in conn.execute(
            'SELECT code,class_id,upload_token FROM slots WHERE class_id=? ORDER BY code', (class_id,))]
    return accounts


def write_credentials(token: str, accounts: list[dict[str, str]], port: int) -> None:
    teacher_url = f'http://127.0.0.1:{port}/teacher/'
    student_url = f'http://127.0.0.1:{port}/student/'
    TEACHER_FILE.write_text(
        f'教师后台：{teacher_url}\n教师账号：admin\n管理密码：{token}\n'
        f'学生后台：{student_url}\n\n'
        '这些是本机演示凭据，已被 Git 忽略。请勿发到群里或提交到仓库。\n',
        encoding='utf-8')
    with ROSTER_FILE.open('w', encoding='utf-8-sig', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(['班级编号', '学生账号', '初始密码', '学生姓名（演示）'])
        for index, account in enumerate(accounts, start=1):
            writer.writerow([account['class_id'], account['code'], account['upload_token'], f'演示学生{index}'])


def main() -> None:
    parser = argparse.ArgumentParser(description='初始化并启动 Code-X-Ai 本地管理后台')
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--students', type=int, default=3, choices=range(1, 26), metavar='1-25')
    parser.add_argument('--init-only', action='store_true')
    args = parser.parse_args()
    token = admin_token()
    service = load_service(token, args.port)
    accounts = seed_demo(service, args.students)
    write_credentials(token, accounts, args.port)
    print(f'\n初始化完成：{TEACHER_FILE}')
    print(f'学生账号名单：{ROSTER_FILE}')
    if args.init_only:
        return
    teacher_url = f'http://127.0.0.1:{args.port}/teacher/'
    student_url = f'http://127.0.0.1:{args.port}/student/'
    print(f'\n教师后台：{teacher_url}')
    print(f'学生后台：{student_url}')
    print('按 Ctrl+C 停止本地服务。')
    webbrowser.open(teacher_url)
    ThreadingHTTPServer(('127.0.0.1', args.port), service.Handler).serve_forever()


if __name__ == '__main__':
    main()
