#!/usr/bin/env python3
"""Restore an off-VPS classroom backup into a temporary directory and audit its contents."""
import argparse
from contextlib import closing
import json
import posixpath
import sqlite3
import tarfile
import tempfile
from pathlib import Path


def verify(archive_path: Path):
    with tempfile.TemporaryDirectory(prefix='codexai-restore-drill-') as folder:
        root=Path(folder)
        with tarfile.open(archive_path,'r:gz') as archive:
            names=archive.getnames()
            members={member.name:member for member in archive.getmembers()}
            if 'var/lib/codexai-uploader/classroom.sqlite3' not in names:
                raise ValueError('备份缺少数据库')
            if not any(name.startswith('srv/codexai-students/') for name in names):
                raise ValueError('备份缺少已发布作品目录')
            archive.extractall(root,filter='data')

        def archived_file_exists(name: str) -> bool:
            direct=members.get(name)
            if direct and direct.isfile():
                return True
            parts=name.split('/')
            for index in range(len(parts)-1,0,-1):
                parent='/'.join(parts[:index])
                member=members.get(parent)
                if member and (member.issym() or member.islnk()):
                    resolved=posixpath.normpath(posixpath.join(posixpath.dirname(parent),member.linkname,
                                                              *parts[index:]))
                    target=members.get(resolved)
                    return bool(target and target.isfile())
            return False
        database=root/'var/lib/codexai-uploader/classroom.sqlite3'
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
            conn.row_factory=sqlite3.Row
            if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('数据库完整性检查失败')
            existing={row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts={table:conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] if table in existing else 0
                    for table in ('slots','submissions','published_works','independent_projects','consultations')}
            courses=conn.execute('''SELECT w.code,l.slug,l.format FROM published_works w
                JOIN lessons l ON l.id=w.lesson_id''').fetchall()
            free=(conn.execute('''SELECT code,id FROM independent_projects
                WHERE published_submission_id IS NOT NULL''').fetchall()
                if 'independent_projects' in existing else [])
        works=root/'srv/codexai-students'
        missing=[]
        for course in courses:
            code=course['code']
            current=(works/'current'/code/'money/index.html' if course['format']=='money'
                     else works/'v2/current'/code/course['slug']/'index.html')
            relative=current.relative_to(root).as_posix()
            if not archived_file_exists(relative):missing.append(relative)
        for item in free:
            current=works/'free/current'/item['code']/str(item['id'])/'index.html'
            relative=current.relative_to(root).as_posix()
            if not archived_file_exists(relative):missing.append(relative)
        zips=list((root/'var/lib/codexai-uploader/archives').rglob('*.zip'))
        if counts['submissions'] and not zips:
            raise ValueError('有提交记录，但备份中没有原始 ZIP')
        if missing:
            raise ValueError('已发布作品缺少当前网页：'+', '.join(missing[:5]))
        return {'archive':str(archive_path.resolve()),'database_integrity':'ok',
                'counts':counts,'original_zips':len(zips),
                'published_course_pages_checked':len(courses),'published_free_pages_checked':len(free),
                'result':'可在临时目录恢复数据库与当前网页'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('archive',type=Path,help='由 backup-vps-classroom.sh 下载的 tar.gz')
    parser.add_argument('--report',type=Path,help='可选 JSON 报告路径')
    args=parser.parse_args()
    try:report=verify(args.archive)
    except (OSError,ValueError,tarfile.TarError,sqlite3.DatabaseError) as exc:
        parser.exit(1,'恢复演练失败：'+str(exc)+'\n')
    output=json.dumps(report,ensure_ascii=False,indent=2)
    if args.report:args.report.write_text(output+'\n')
    print(output)


if __name__=='__main__':main()
