"""End-to-end API smoke test without touching the real VPS."""
import importlib.util
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
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
            with urlopen(req) as resp: code, body, kind = resp.status,resp.read(),resp.headers.get('Content-Type')
        except HTTPError as exc:
            code, body, kind = exc.code,exc.read(),exc.headers.get('Content-Type')
            exc.close()
        self.assertEqual(code,status,body[:500])
        return body if kind == 'image/png' or kind.startswith('text/') else json.loads(body)

    def test_submit_review_publish_and_resubmit(self):
        admin = {'X-Admin-Token':os.environ['CODEXAI_ADMIN_TOKEN']}
        self.call('/api/admin/classes','POST',json.dumps({'class_id':'c260924a','count':2}).encode(),admin|{'Content-Type':'application/json'},201)
        slots = self.call('/api/admin/slots',headers=admin)
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
        self.assertEqual(published['url'],f'https://codexai.site/works/{code}/money/')
        self.assertTrue((self.app.WORKS/'current'/code/'money/index.html').is_file())
        self.assertEqual(self.call('/api/status/'+code,headers=upload_headers)['status'],'已发布')
        self.assertTrue(self.call('/api/works/'+code+'/qr.png')[:8] == b'\x89PNG\r\n\x1a\n')
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


if __name__ == '__main__': unittest.main()
