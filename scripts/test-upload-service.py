"""End-to-end API smoke test without touching the real VPS."""
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent


class UploadFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ['CODEXAI_DATA_DIR'] = cls.temp.name + '/data'
        os.environ['CODEXAI_WORKS_DIR'] = cls.temp.name + '/works'
        os.environ['CODEXAI_ADMIN_TOKEN'] = 'test-admin-secret-is-at-least-24-chars'
        spec = importlib.util.spec_from_file_location('uploader', ROOT/'scripts/upload-service.py')
        cls.app = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.app)
        cls.app.init()
        cls.server = ThreadingHTTPServer(('127.0.0.1',0), cls.app.Handler)
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.temp.cleanup()

    def call(self, path, method='GET', data=None, headers=None, status=200):
        req = Request(self.base+path, data=data, method=method, headers=headers or {})
        try:
            with urlopen(req) as resp:
                code, body, kind = resp.status,resp.read(),resp.headers.get('Content-Type')
                self.last_headers = resp.headers
        except HTTPError as exc:
            code, body, kind = exc.code,exc.read(),exc.headers.get('Content-Type')
            self.last_headers = exc.headers
            exc.close()
        self.assertEqual(code,status,body[:500])
        return body if kind in ('image/png','application/zip') or kind.startswith(('text/','application/xml')) else json.loads(body)

    def test_submit_review_publish_and_resubmit(self):
        admin = {'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        self.call('/api/admin/classes','POST',json.dumps({'class_id':'c260924a','count':2}).encode(),admin|{'Content-Type':'application/json'},201)
        slots = [s for s in self.call('/api/admin/slots',headers=admin) if s['class_id']=='c260924a']
        self.assertEqual(len(slots),2)
        roster = self.call('/api/admin/roster.csv?class_id=c260924a',headers=admin)
        self.assertIn(b'c260924a-s01',roster)
        code,token = slots[0]['code'],slots[0]['upload_token']
        zip_data = (ROOT/'codexai-site/dist/classroom/零花钱计划师-起始包.zip').read_bytes()
        upload_headers = {'X-Upload-Token':token,'Content-Type':'application/zip'}
        self.call('/api/submit/'+code,'POST',zip_data,upload_headers|{'X-Upload-Token':'wrong'},403)
        first = self.call('/api/submit/'+code,'POST',zip_data,upload_headers,201)
        self.assertEqual(first['status'],'待审核')
        self.assertEqual(self.call('/api/status/'+code,headers=upload_headers)['status'],'待审核')
        current = next(x for x in self.call('/api/admin/slots',headers=admin) if x['code']==code)
        preview = self.call('/preview/'+current['preview_token']+'/money/',headers={})
        self.assertIn('零花钱计划师',preview.decode() if isinstance(preview,bytes) else preview)
        second = self.call('/api/submit/'+code,'POST',zip_data,upload_headers,201)
        self.call('/api/admin/publish/'+str(first['id']),'POST',b'',admin,409)
        published = self.call('/api/admin/publish/'+str(second['id']),'POST',b'',admin)
        self.assertTrue(any(event['submission_id']==second['id'] for event in self.call('/api/admin/publication-events',headers=admin)))
        share_path=urlsplit(published['url']).path
        self.assertRegex(share_path,r'^/share/[A-Za-z0-9_-]{32,64}/$')
        self.assertTrue((self.app.WORKS/'current'/code/'money/index.html').is_file())
        self.assertIn('零花钱计划师',self.call(share_path+'money/').decode())
        self.call(f'/works/{code}/money/',status=404)
        self.assertEqual(self.call('/api/public/showcase'),[])
        self.assertEqual(self.call('/api/status/'+code,headers=upload_headers)['status'],'已发布')
        self.assertTrue(self.call(urlsplit(published['qr']).path)[:8] == b'\x89PNG\r\n\x1a\n')
        other = slots[1]
        submitted = self.call('/api/submit/'+other['code'],'POST',zip_data,{'X-Upload-Token':other['upload_token'],'Content-Type':'application/zip'},201)
        self.call('/api/admin/reject/'+str(submitted['id']),'POST',json.dumps({'reason':'请改好标题'}).encode(),admin|{'Content-Type':'application/json'})
        state = self.call('/api/status/'+other['code'],headers={'X-Upload-Token':other['upload_token']})
        self.assertEqual(state['status'],'需修改')

    def test_twenty_students_can_submit_together(self):
        admin = {'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        self.call('/api/admin/classes','POST',json.dumps({'class_id':'c260924b','count':20}).encode(),admin|{'Content-Type':'application/json'},201)
        slots = [slot for slot in self.call('/api/admin/slots',headers=admin) if slot['class_id']=='c260924b']
        zip_data = (ROOT/'codexai-site/dist/classroom/零花钱计划师-起始包.zip').read_bytes()
        def send(slot):
            return self.call('/api/submit/'+slot['code'],'POST',zip_data,
                {'X-Upload-Token':slot['upload_token'],'Content-Type':'application/zip'},201)
        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(send,slots))
        self.assertEqual([row['status'] for row in results],['待审核']*20)

    def test_student_portal_multiple_topics_and_public_gallery(self):
        admin={'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        self.call('/api/admin/classes','POST',json.dumps({'class_id':'c260924c','count':2}).encode(),admin|{'Content-Type':'application/json'},201)
        camp_slots=[s for s in self.call('/api/admin/slots',headers=admin) if s['class_id']=='c260924c']
        slot,other=camp_slots
        program=self.call('/api/admin/programs','POST',json.dumps({'slug':'summer-test','title':'暑期创作营','kind':'camp','days':8,'description':'八天'}).encode(),admin|{'Content-Type':'application/json'},201)
        lesson=self.call('/api/admin/lessons','POST',json.dumps({'program_id':program['id'],'slug':'story-test','title':'互动故事','day_no':2}).encode(),admin|{'Content-Type':'application/json'},201)
        self.call('/api/admin/enroll-student','POST',json.dumps({'code':slot['code'],'program_id':program['id']}).encode(),admin|{'Content-Type':'application/json'})
        zip_bytes=io.BytesIO()
        with ZipFile(zip_bytes,'w') as z:
            z.writestr('my-project/index.html','<!doctype html><html><head><title>测试故事</title></head><body><h1>故事开始</h1></body></html>')
            z.writestr('my-project/style.css','body{color:green}')
        starter=zip_bytes.getvalue()
        self.call('/api/admin/lessons/'+str(lesson['id'])+'/starter','POST',starter,admin|{'Content-Type':'application/zip'})
        self.call('/api/student/login','POST',json.dumps({'code':other['code'],'token':other['upload_token']}).encode(),
                  {'Origin':'https://www.codexai.site','Content-Type':'application/json'})
        other_cookie=self.last_headers.get('Set-Cookie').split(';',1)[0]
        other_dashboard=self.call('/api/student/dashboard',headers={'Cookie':other_cookie})
        self.assertEqual({item['lesson_slug'] for item in other_dashboard['lessons']},{'money'})
        self.call('/api/student/login','POST',json.dumps({'code':slot['code'],'token':'wrong'}).encode(),
                  {'Origin':'https://www.codexai.site','Content-Type':'application/json'},403)
        self.call('/api/student/login','POST',json.dumps({'code':slot['code'],'token':slot['upload_token']}).encode(),
                  {'Origin':'https://www.codexai.site','Content-Type':'application/json'})
        cookie=self.last_headers.get('Set-Cookie').split(';',1)[0]
        student={'Cookie':cookie,'Origin':'https://www.codexai.site'}
        dashboard=self.call('/api/student/dashboard',headers=student)
        self.assertEqual({item['lesson_slug'] for item in dashboard['lessons']},{'money','story-test'})
        self.assertEqual(self.call('/api/student/lessons/'+str(lesson['id'])+'/starter.zip',headers=student)[:2],b'PK')
        self.call('/api/student/submit/'+str(lesson['id']),'POST',starter,
                  student|{'Origin':'https://codexai.site','Content-Type':'application/zip'},403)
        first=self.call('/api/student/submit/'+str(lesson['id']),'POST',starter,student|{'Content-Type':'application/zip'},201)
        self.call('/api/admin/reject/'+str(first['id']),'POST',json.dumps({'reason':'请补一个按钮'}).encode(),admin|{'Content-Type':'application/json'})
        self.assertEqual(next(x for x in self.call('/api/student/dashboard',headers=student)['lessons'] if x['lesson_slug']=='story-test')['status'],'需修改')
        second=self.call('/api/student/submit/'+str(lesson['id']),'POST',starter,student|{'Content-Type':'application/zip'},201)
        published=self.call('/api/admin/publish/'+str(second['id']),'POST',b'',admin)
        share_path=urlsplit(published['url']).path
        self.assertRegex(share_path,r'^/share/[A-Za-z0-9_-]{32,64}/$')
        self.assertIn('测试故事',self.call(share_path).decode())
        self.call(f'/projects/{slot["code"]}/story-test/',status=404)
        self.assertTrue((self.app.WORKS/'v2/current'/slot['code']/'story-test'/'index.html').is_file())
        self.call('/api/admin/collections','POST',json.dumps({'code':other['code'],'program_id':program['id'],
            'active':True}).encode(),admin|{'Content-Type':'application/json'},403)
        collection=self.call('/api/admin/collections','POST',json.dumps({'code':slot['code'],
            'program_id':program['id'],'active':True}).encode(),admin|{'Content-Type':'application/json'})
        collection_path=urlsplit(collection['url']).path
        self.assertIn('互动故事',self.call(collection_path).decode())
        self.assertIn(collection['url'],[item['url'] for item in self.call('/api/student/dashboard',headers=student)['collections']])
        self.assertIn(collection['url'],[item['url'] for item in self.call('/api/admin/collections',headers=admin)])
        self.assertNotIn(collection_path,self.call('/sitemap.xml').decode())
        self.call('/api/admin/collections','POST',json.dumps({'code':slot['code'],
            'program_id':program['id'],'active':False}).encode(),admin|{'Content-Type':'application/json'})
        self.call(collection_path,status=404)
        self.assertNotIn(slot['code'],[x['code'] for x in self.call('/api/public/showcase')])
        self.call('/api/admin/visibility/'+slot['code']+'/'+str(lesson['id']),'POST',json.dumps({'listed':True}).encode(),admin|{'Content-Type':'application/json'},409)
        consent=self.call('/api/admin/consents','POST',json.dumps({'code':slot['code'],'lesson_id':lesson['id'],
            'independent_id':None,'guardian_ref':'S01 家长','channel':'现场签署','consent_at':'2026-09-24',
            'evidence_ref':'本地同意表 01'}).encode(),admin|{'Content-Type':'application/json'},201)
        self.call('/api/admin/visibility/'+slot['code']+'/'+str(lesson['id']),'POST',json.dumps({'listed':True}).encode(),admin|{'Content-Type':'application/json'})
        gallery=next(x for x in self.call('/api/public/showcase') if x['code']==slot['code'])
        gallery_path=urlsplit(gallery['url']).path
        self.assertTrue(gallery_path.startswith('/gallery/'))
        self.assertIn('测试故事',self.call(gallery_path).decode())
        self.assertIn(gallery_path,self.call('/sitemap.xml').decode())
        revision=self.call('/api/student/submit/'+str(lesson['id']),'POST',starter,
                           student|{'Content-Type':'application/zip'},201)
        republished=self.call('/api/admin/publish/'+str(revision['id']),'POST',b'',admin)
        self.assertEqual(republished['url'],published['url'])
        self.assertNotIn(slot['code'],[x['code'] for x in self.call('/api/public/showcase')])
        self.call(gallery_path,status=404)
        self.assertNotIn(gallery_path,self.call('/sitemap.xml').decode())
        self.call('/api/admin/visibility/'+slot['code']+'/'+str(lesson['id']),'POST',json.dumps({'listed':True}).encode(),
                  admin|{'Content-Type':'application/json'},409)
        self.call('/api/admin/consents/'+str(consent['id'])+'/revoke','POST',b'',admin)
        self.assertNotIn(slot['code'],[x['code'] for x in self.call('/api/public/showcase')])
        self.call('/api/admin/visibility/'+slot['code']+'/'+str(lesson['id']),'POST',json.dumps({'listed':False}).encode(),admin|{'Content-Type':'application/json'})
        self.assertNotIn(slot['code'],[x['code'] for x in self.call('/api/public/showcase')])
        self.assertTrue(self.call(urlsplit(published['qr']).path)[:8]==b'\x89PNG\r\n\x1a\n')
        with self.app.db() as conn:
            conn.execute('UPDATE published_works SET legacy_allowed=1 WHERE code=? AND lesson_id=?',
                         (slot['code'],lesson['id']))
        self.assertIn('测试故事',self.call(f'/projects/{slot["code"]}/story-test/').decode())
        self.call(f'/api/admin/course/{lesson["id"]}/share','POST',
                  json.dumps({'code':slot['code'],'active':False}).encode(),admin|{'Content-Type':'application/json'})
        self.call(f'/projects/{slot["code"]}/story-test/',status=404)
        self.call(share_path,status=404)

    def test_independent_project_versions_and_revocable_family_link(self):
        admin={'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        self.call('/api/admin/classes','POST',json.dumps({'class_id':'c260924d','count':1}).encode(),admin|{'Content-Type':'application/json'},201)
        slot=next(x for x in self.call('/api/admin/slots',headers=admin) if x['class_id']=='c260924d')
        self.call('/api/student/login','POST',json.dumps({'code':slot['code'],'token':slot['upload_token']}).encode(),
                  {'Origin':'https://www.codexai.site','Content-Type':'application/json'})
        cookie=self.last_headers.get('Set-Cookie').split(';',1)[0]
        student={'Cookie':cookie,'Origin':'https://www.codexai.site'}
        self.call('/api/student/independent','POST',json.dumps({'title':'我的故事','summary':'帮助朋友选择故事结局',
            'category':'互动故事'}).encode(),{'Origin':'https://www.codexai.site','Content-Type':'application/json'},401)
        project=self.call('/api/student/independent','POST',json.dumps({'title':'我的故事','summary':'帮助朋友选择故事结局',
            'category':'互动故事'}).encode(),student|{'Content-Type':'application/json'},201)
        self.assertEqual(len(self.call('/api/student/independent',headers=student)),1)
        archive=io.BytesIO()
        with ZipFile(archive,'w') as zipped:
            zipped.writestr('my-story/index.html','<!doctype html><html><head><title>自由故事</title></head><body><h1>自由故事</h1></body></html>')
        submitted=self.call(f'/api/student/independent/{project["id"]}/submit','POST',archive.getvalue(),
                            student|{'Content-Type':'application/zip'},201)
        pending=next(x for x in self.call('/api/admin/independent',headers=admin) if x['id']==project['id'])
        self.assertEqual(pending['status'],'待审核')
        self.assertIn('自由故事',self.call(urlsplit(pending['preview_url']).path).decode())
        published=self.call('/api/admin/publish/'+str(submitted['id']),'POST',b'',admin)
        first_url=published['url']
        self.assertIn('自由故事',self.call(urlsplit(first_url).path).decode())
        self.assertEqual(self.call('/api/public/showcase'),[])
        second=self.call(f'/api/student/independent/{project["id"]}/submit','POST',archive.getvalue(),
                         student|{'Content-Type':'application/zip'},201)
        self.assertIn('自由故事',self.call(urlsplit(first_url).path).decode())
        self.call('/api/admin/reject/'+str(second['id']),'POST',json.dumps({'reason':'再加一个选择按钮'}).encode(),
                  admin|{'Content-Type':'application/json'})
        status=self.call('/api/student/independent',headers=student)[0]
        self.assertEqual(status['status'],'需修改')
        self.assertEqual(status['url'],first_url)
        self.call(f'/api/admin/independent/{project["id"]}/share','POST',json.dumps({'active':False}).encode(),
                  admin|{'Content-Type':'application/json'})
        self.call(urlsplit(first_url).path,status=404)
        refreshed=self.call(f'/api/admin/independent/{project["id"]}/share','POST',json.dumps({'active':True}).encode(),
                            admin|{'Content-Type':'application/json'})
        self.assertNotEqual(refreshed['url'],first_url)
        self.assertIn('自由故事',self.call(urlsplit(refreshed['url']).path).decode())
        replacement=io.BytesIO()
        with ZipFile(replacement,'w') as zipped:
            zipped.writestr('index.html','<!doctype html><html><head><title>新版故事</title></head><body><h1>新版故事</h1></body></html>')
        third=self.call(f'/api/student/independent/{project["id"]}/submit','POST',replacement.getvalue(),
                        student|{'Content-Type':'application/zip'},201)
        self.call('/api/admin/publish/'+str(third['id']),'POST',b'',admin)
        share_path=urlsplit(refreshed['url']).path
        self.assertIn('新版故事',self.call(share_path).decode())
        versions=self.call(f'/api/admin/versions?code={slot["code"]}&kind=independent&id={project["id"]}',headers=admin)
        self.assertEqual(versions[0]['id'],third['id'])
        self.assertEqual(versions[-1]['id'],submitted['id'])
        self.call('/api/admin/rollback/'+str(submitted['id']),'POST',b'',admin)
        self.assertIn('自由故事',self.call(share_path).decode())
        self.assertEqual(self.call('/api/public/showcase'),[])

    def test_consultation_requires_consent_and_is_only_visible_to_teacher(self):
        admin={'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        body={'parent_name':'王女士','contact_kind':'微信','contact':'parent-wang-01','child_age':'11 岁',
              'interest':'零花钱计划师','message':'想了解周末的课','source':'channel-a',
              'entry_path':'/consult/','company':'','consent':True}
        headers={'Origin':'https://codexai.site','Content-Type':'application/json'}
        self.call('/api/public/consultations','POST',json.dumps(body).encode(),
                  headers|{'Origin':'https://another.example'},403)
        self.call('/api/public/consultations','POST',json.dumps(body|{'consent':False}).encode(),headers,400)
        self.call('/api/public/consultations','POST',json.dumps(body).encode(),headers,201)
        self.call('/api/public/consultations','POST',json.dumps(body).encode(),headers,201)
        self.call('/api/admin/consultations',headers={},status=401)
        leads=[x for x in self.call('/api/admin/consultations',headers=admin) if x['contact']=='parent-wang-01']
        self.assertEqual(len(leads),1)
        self.assertEqual(leads[0]['source'],'channel-a')
        lead_id=leads[0]['id']
        self.call(f'/api/admin/consultations/{lead_id}','POST',json.dumps({'status':'已联系','note':'已微信回复'}).encode(),
                  admin|{'Content-Type':'application/json'})
        csv_data=self.call('/api/admin/consultations.csv',headers=admin)
        self.assertIn('parent-wang-01',csv_data.decode())
        self.call(f'/api/admin/consultations/{lead_id}/delete','POST',b'',admin)
        self.assertFalse(any(x['id']==lead_id for x in self.call('/api/admin/consultations',headers=admin)))

    def test_public_courses_require_manual_marketing_publication(self):
        admin={'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        program=self.call('/api/admin/programs','POST',json.dumps({'slug':'camp-test','title':'八天创作营',
            'kind':'camp','days':8,'description':'逐日完成作品'}).encode(),admin|{'Content-Type':'application/json'},201)
        self.assertNotIn('camp-test',[row['slug'] for row in self.call('/api/public/courses')])
        self.call('/courses/camp-test/',status=404)
        details={'status':'consulting','summary':'孩子每天完成一个自己的网页作品。',
            'audience':'10–14 岁零基础孩子','outcome':'一个可以带回家的作品集',
            'duration':'8 天创作营','parent_role':'家长在结营时测试孩子的作品'}
        path=f'/api/admin/programs/{program["id"]}/marketing'
        self.call(path,'POST',json.dumps(details|{'outcome':''}).encode(),admin|{'Content-Type':'application/json'},400)
        self.call(path,'POST',json.dumps(details).encode(),admin|{'Content-Type':'application/json'},409)
        self.call('/api/admin/lessons','POST',json.dumps({'program_id':program['id'],'slug':'camp-day-one',
            'title':'第一天的网页','day_no':1}).encode(),admin|{'Content-Type':'application/json'},201)
        self.call(path,'POST',json.dumps(details).encode(),admin|{'Content-Type':'application/json'})
        self.assertIn('camp-test',[row['slug'] for row in self.call('/api/public/courses')])
        page=self.call('/courses/camp-test/').decode()
        self.assertIn('八天创作营',page)
        self.assertIn('第一天的网页',page)
        self.assertIn('/courses/camp-test/',self.call('/sitemap.xml').decode())
        self.call(path,'POST',json.dumps(details|{'status':'paused'}).encode(),admin|{'Content-Type':'application/json'})
        self.assertNotIn('camp-test',[row['slug'] for row in self.call('/api/public/courses')])
        self.assertIn('暂停咨询',self.call('/courses/camp-test/').decode())
        self.assertNotIn('/courses/camp-test/',self.call('/sitemap.xml').decode())

    def test_site_content_and_qr_are_teacher_managed(self):
        admin={'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        original=self.call('/api/public/site-content')
        self.assertTrue(len(original['faqs'])>=5)
        self.assertIn('我不是 IT 专业出身',original['teacher_intro'])
        self.assertIn('/about/',self.call('/sitemap.xml').decode())
        self.assertFalse(original['wechat_qr_available'])
        self.call('/api/admin/site-content',headers={},status=401)
        updated={'teacher_intro':'真实老师介绍会在取得资料后填写。',
                 'demo_title':'首课教师示范','demo_summary':'用一个示范工具了解作品交付。',
                 'faqs':[{'q':'如何联系老师？','a':'可以到咨询页复制微信号联系老师。'}]}
        self.call('/api/admin/site-content','POST',json.dumps(updated).encode(),
                  admin|{'Content-Type':'application/json'})
        content=self.call('/api/public/site-content')
        self.assertEqual(content['faqs'],updated['faqs'])
        self.assertEqual(content['demo_title'],updated['demo_title'])
        self.call('/api/admin/wechat-qr','POST',b'not an image',admin|{'Content-Type':'image/png'},400)
        from PIL import Image
        picture=io.BytesIO();Image.new('RGB',(180,180),'white').save(picture,'PNG')
        self.call('/api/admin/wechat-qr','POST',picture.getvalue(),admin|{'Content-Type':'image/png'})
        self.assertTrue(self.call('/api/public/site-content')['wechat_qr_available'])
        self.assertEqual(self.call('/api/public/wechat-qr')[:8],b'\x89PNG\r\n\x1a\n')


class ExistingSiteMigration(unittest.TestCase):
    def test_existing_public_work_is_hidden_but_old_link_remains_available(self):
        with tempfile.TemporaryDirectory() as folder:
            previous={name:os.environ.get(name) for name in ('CODEXAI_DATA_DIR','CODEXAI_WORKS_DIR','CODEXAI_ADMIN_TOKEN')}
            os.environ['CODEXAI_DATA_DIR']=folder+'/data'
            os.environ['CODEXAI_WORKS_DIR']=folder+'/works'
            os.environ['CODEXAI_ADMIN_TOKEN']='migration-secret-is-at-least-24-chars'
            try:
                spec=importlib.util.spec_from_file_location('migration_uploader',ROOT/'scripts/upload-service.py')
                app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
                app.init()
                with app.db() as conn:
                    lesson_id=conn.execute('SELECT id FROM lessons WHERE slug=?',('money',)).fetchone()['id']
                    conn.execute('INSERT INTO slots(code,class_id,upload_token,created_at) VALUES (?,?,?,?)',
                                 ('old-student','old-class','old-token',app.now()))
                    sid=conn.execute('''INSERT INTO submissions(code,lesson_id,received_at,status,preview_token)
                        VALUES (?,?,?,?,?)''',('old-student',lesson_id,app.now(),'已发布','old-preview-token')).lastrowid
                    conn.execute('DROP TABLE published_works')
                    conn.execute('''CREATE TABLE published_works (
                        code TEXT NOT NULL REFERENCES slots(code), lesson_id INTEGER NOT NULL REFERENCES lessons(id),
                        submission_id INTEGER NOT NULL REFERENCES submissions(id), url TEXT NOT NULL,
                        listed INTEGER NOT NULL DEFAULT 1, published_at TEXT NOT NULL,
                        PRIMARY KEY(code,lesson_id))''')
                    conn.execute('''INSERT INTO published_works VALUES (?,?,?,?,?,?)''',
                                 ('old-student',lesson_id,sid,app.work_url('old-student'),1,app.now()))
                release=app.WORKS/'releases/old-student/initial';(release/'money').mkdir(parents=True)
                (release/'money/index.html').write_text('<html>existing</html>')
                (app.WORKS/'current/old-student').symlink_to('../releases/old-student/initial')
                app.init()
                with app.db() as conn:
                    work=conn.execute('SELECT * FROM published_works WHERE code=?',('old-student',)).fetchone()
                    self.assertEqual(work['listed'],0)
                    self.assertEqual(work['legacy_allowed'],1)
                    self.assertTrue(work['url'].startswith('https://codexai.site/share/'))
            finally:
                for name,value in previous.items():
                    if value is None:os.environ.pop(name,None)
                    else:os.environ[name]=value


if __name__ == '__main__': unittest.main()
