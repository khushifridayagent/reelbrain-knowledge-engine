import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from studio.api import create_app
from studio.core import SearchIndex,Document
from test_studio import FakeModels

class FakeDB:
    def stats(self,f):return {'total':2,'completed':1}
    def submit(self,url):return {'job_id':7,'source_url':url,'status':'queued','inserted':True}
class FakeLLM:
    def plan(self,q):return [q,'trading automation'],'search'
    def summarize(self,q,cards,web=(),detail=False):return {'answer':'Saved evidence [S1]','citations':['S1']} if cards else None
    def map_reduce(self,q,cards):return self.summarize(q,cards)
class FakeResearch:
    def run(self,q,urls):return {'documents':[{'url':'https://github.com/owner/project','title':'Public repo','kind':'github_metadata','text':'Public evidence'}],'warnings':[]}
class Services:
    def __init__(self,path):
        self.db=FakeDB();self.llm=FakeLLM();self.research=FakeResearch();self.index=SearchIndex(path,FakeModels())
        self.lock=__import__('threading').Lock()
        for id,url,body in [('a','https://www.instagram.com/reel/Abcd/','Alpaca trading workflow'),('b','https://www.instagram.com/p/Efgh/','Image automation')]:
            self.index.replace_source(url,[Document(id,url,'creator','2026-11-01','2026-11-25','completed','ocr','slide:1',body)],'1')
    def open(self):pass
    def refresh(self):return {'changed':0,'more_pending':False}
class API(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'STUDIO_BACKEND_TOKEN':'x'*32});self.env.start();self.s=Services(Path(self.tmp.name)/'i.sqlite');self.client=TestClient(create_app(self.s));self.auth={'Authorization':'Bearer '+'x'*32}
    def tearDown(self):self.client.close();self.s.index.con.close();self.env.stop();self.tmp.cleanup()
    def test_all_data_routes_require_auth(self):
        for endpoint in ('search','detail','submit','counts'):
            self.assertEqual(self.client.post('/'+endpoint,json={}).status_code,401)
        self.assertEqual(self.client.get('/docs').status_code,404)
    def test_search_and_context_are_isolated(self):
        r=self.client.post('/search',headers=self.auth,json={'question':'trading automation'});self.assertEqual(r.status_code,200);self.assertIn('sources',r.json());self.assertEqual(r.headers['cache-control'],'no-store')
        r=self.client.post('/detail',headers=self.auth,json={'question':'features','search_context':'Alpaca','sources':['https://www.instagram.com/reel/Abcd/'],'public_query':'Alpaca API','research':True});self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['sources']),1);self.assertEqual(r.json()['sources'][0]['source'],'https://www.instagram.com/reel/Abcd/');self.assertEqual(len(r.json()['public_sources']),1)
    def test_submit_and_count(self):
        r=self.client.post('/submit',headers=self.auth,json={'url':'https://instagram.com/p/Abcd/?igsh=secret'});self.assertEqual(r.status_code,200);self.assertEqual(r.json()['source_url'],'https://www.instagram.com/p/Abcd/')
        r=self.client.post('/submit',headers=self.auth,json={'url':'https://evil.com/reel/Abcd/'});self.assertEqual(r.status_code,422)
        r=self.client.post('/search',headers=self.auth,json={'question':'count reels','mode':'count'});self.assertEqual(r.json()['counts']['total'],2)
    def test_research_rejects_secret_url(self):
        r=self.client.post('/detail',headers=self.auth,json={'question':'features','sources':['https://www.instagram.com/reel/Abcd/'],'research':True,'public_query':'https://private.example/?token=secret'});self.assertEqual(r.status_code,422)
