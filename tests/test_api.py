import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import app

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); app.DATA=Path(cls.tmp.name)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base='http://127.0.0.1:'+str(cls.server.server_port)
        cls.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def request(self,path,data=None,token=True):
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**({'X-Zynx-Token':app.TOKEN} if token else {})})
        with self.opener.open(req,timeout=5) as response:return response.read()
    def create_meeting(self):
        payload=json.loads(self.request('/api/examples'))[0]|{'mode':'rules'}
        job=json.loads(self.request('/api/analyze',payload))['job_id']
        for _ in range(100):
            state=json.loads(self.request('/api/jobs/'+job))
            if state['state']!='running':break
            time.sleep(.02)
        self.assertEqual(state['state'],'done',state)
        return state['result']
    def test_full_text_save_reload_export(self):
        meeting=self.create_meeting(); tasks=meeting['result']['tasks']
        self.assertEqual(len(tasks),3)
        self.assertEqual(tasks[0]['due_date'],'2026-10-07')
        self.assertEqual(tasks[1]['due_date'],'2026-09-25')
        self.assertIsNone(tasks[2]['due_date'])
        tasks[0]['reviewed']=True;tasks[0]['status']='Выполнено'
        self.request('/api/save',{'id':meeting['id'],'tasks':tasks})
        saved=json.loads(self.request('/api/meetings/'+meeting['id']))
        self.assertEqual(saved['result']['tasks'][0]['status'],'Выполнено')
        self.assertTrue(saved['result']['tasks'][0]['reviewed'])
        self.assertEqual(json.loads(self.request('/api/meetings/'+meeting['id']+'/json'))['id'],meeting['id'])
        self.request('/api/delete',{'id':meeting['id']})
        self.assertNotIn(meeting['id'],[m['id'] for m in json.loads(self.request('/api/meetings'))])
    def test_csrf_required(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/analyze',{'transcript':'hi'},token=False)
        self.assertEqual(caught.exception.code,403)
    def test_recording_consent_required(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:self.request('/api/transcribe',{'consent':False})
        self.assertEqual(caught.exception.code,400)
    def test_static_and_config(self):
        self.assertIn(b'ZYNX Minutes',self.request('/'))
        self.assertIn('csrf',json.loads(self.request('/api/config')))
    @unittest.skipUnless(importlib.util.find_spec('docx') and importlib.util.find_spec('reportlab'),'Export dependencies not installed')
    def test_document_export_bytes(self):
        meeting=self.create_meeting()
        self.assertTrue(self.request('/api/meetings/'+meeting['id']+'/pdf').startswith(b'%PDF-'))
        self.assertTrue(self.request('/api/meetings/'+meeting['id']+'/docx').startswith(b'PK'))

if __name__=='__main__':unittest.main()
