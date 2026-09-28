#!/usr/bin/env python3
"""External read-only checks for the public site, classroom API and consultation page."""
import json
import subprocess
import sys

CHECKS=[
    ('首页','https://codexai.site/',b'Code-X-Ai'),
    ('关于我','https://codexai.site/about/',b'code-x-ai-avatar.png'),
    ('课程','https://codexai.site/courses/',b'\xe8\xaf\xbe\xe7\xa8\x8b'),
    ('咨询页','https://codexai.site/consult/',b'consult-form'),
    ('咨询与作品数据库','https://codexai.site/api/health',b'"ok": true'),
    ('独立站内容','https://codexai.site/api/public/site-content',b'teacher_intro'),
    ('公开课程接口','https://codexai.site/api/public/courses',b'['),
    ('教师后台','https://www.codexai.site/teacher/',b'id="login-form"'),
    ('学生后台','https://www.codexai.site/student/',b'CODEXAI'),
]


def run(checks=CHECKS):
    results=[]
    for name,url,needle in checks:
        try:
            result=subprocess.run(['curl','--fail','--silent','--show-error','--location',
                                   '--retry','1','--retry-all-errors','--retry-delay','1',
                                   '--max-time','12','--write-out','\n%{http_code}',
                                   '--user-agent','CodexAI-ReadOnlyHealthCheck/1',url],
                                  capture_output=True,timeout=15,check=False)
            body,_,status=result.stdout.rpartition(b'\n')
            code=int(status) if status.isdigit() else 0
            ok=result.returncode==0 and code==200 and needle in body
            item={'name':name,'url':url,'status':code,'ok':ok}
            if result.returncode:item['error']=result.stderr.decode(errors='replace')[:200]
            results.append(item)
        except (OSError,subprocess.TimeoutExpired) as exc:
            results.append({'name':name,'url':url,'ok':False,'error':str(exc)[:200]})
    return results


if __name__=='__main__':
    result=run()
    print(json.dumps({'ok':all(item['ok'] for item in result),'checks':result},ensure_ascii=False,indent=2))
    sys.exit(0 if all(item['ok'] for item in result) else 1)
