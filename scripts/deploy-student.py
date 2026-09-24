#!/usr/bin/env python3
"""Manual fallback: submit a teacher-reviewed money project through the audited API."""
import argparse
import json
import ssl
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZIP_DEFLATED, ZipFile

ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser()
parser.add_argument('code')
parser.add_argument('project',type=Path)
parser.add_argument('--base-url',default='https://codexai.site')
args=parser.parse_args()
admin_file=ROOT/'preparation/.teacher-admin-token'
if not admin_file.is_file():parser.error('教师密钥文件不存在，请先使用教师工作台初始化')
admin=admin_file.read_text().strip()
if len(admin)<24:parser.error('教师密钥文件不完整')
try:
    import certifi
    tls_context=ssl.create_default_context(cafile=certifi.where())
except ImportError:
    tls_context=ssl.create_default_context()

def request(path,method='GET',data=None,headers=None,raw=False):
    req=Request(args.base_url+path,data=data,method=method,headers=headers or {})
    try:
        with urlopen(req,timeout=45,context=tls_context) as response:
            body=response.read()
    except HTTPError as exc:
        body=exc.read()
        try:message=json.loads(body).get('error','请求失败')
        except ValueError:message=body[:200].decode(errors='replace')
        raise SystemExit(f'服务器拒绝：{message}') from exc
    return body if raw else json.loads(body)

slots=request('/api/admin/slots',headers={'X-Admin-Token':admin})
slot=next((row for row in slots if row['code']==args.code),None)
if not slot:parser.error('学生编号不存在，请先在教师工作台建班')
with tempfile.TemporaryDirectory() as folder:
    archive=Path(folder)/'reviewed.zip'
    if args.project.is_file() and args.project.suffix.lower()=='.zip':
        archive=args.project
    elif args.project.is_dir():
        with ZipFile(archive,'w',ZIP_DEFLATED) as zipped:
            for item in sorted(args.project.rglob('*')):
                if item.is_symlink():parser.error('项目文件夹不能包含符号链接')
                if item.is_file():zipped.write(item,item.relative_to(args.project).as_posix())
    else:parser.error('请输入学生项目 ZIP 或文件夹')
    submitted=request('/api/submit/'+args.code,'POST',archive.read_bytes(),
                      {'X-Upload-Token':slot['upload_token'],'Content-Type':'application/zip'})
    result=request('/api/admin/publish/'+str(submitted['id']),'POST',b'',{'X-Admin-Token':admin})
    qr=request(result['qr'].removeprefix(args.base_url),raw=True)
    output=ROOT/'preparation/二维码/学生作品'/f'{args.code}.png'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(qr)
    print('作品已发布：'+result['url'])
    print('二维码：'+str(output))
