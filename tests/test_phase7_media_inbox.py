"""Test-first: media only from an explicit authorized upload, not scraped DM group."""
import io, tempfile, unittest
from pathlib import Path
from PIL import Image
from reelbrain.media_inbox import MediaInbox,MediaInboxError
from reelbrain.store import KnowledgeStore
from fastapi.testclient import TestClient
from reelbrain.webapp import create_app

URL='https://www.instagram.com/reel/Abc111/'

def image_bytes():
    x=Image.new('RGB',(320,80),'white')
    file=io.BytesIO();x.save(file,'PNG');return file.getvalue()

class StubEngine:
    def ingest(self,media_path,source_url,tenant,allow_external=False):
        assert Path(media_path).is_file()
        assert source_url==URL
        assert not allow_external
        return {'status':'evidence_saved','resource_count':1,'stage_timings_ms':{'ocr':1}}

class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db_path=Path(self.tmp.name)/'data.db'
        self.media_dir=Path(self.tmp.name)/'private_media'
    def tearDown(self):self.tmp.cleanup()
    def test_upload_deduplication_and_processing_receipt(self):
        with MediaInbox(self.db_path,self.media_dir) as inbox:
            one=inbox.save_upload(io.BytesIO(image_bytes()),'clip.png',URL)
            again=inbox.save_upload(io.BytesIO(image_bytes()),'clip.png',URL)
            self.assertEqual(one['task_id'],again['task_id'])
            self.assertEqual(one['status'],'queued')
            done=inbox.process_one(one['task_id'],engine=StubEngine())
            self.assertEqual(done['status'],'complete')
            self.assertEqual(inbox.get(one['task_id'])['status'],'complete')
            self.assertEqual(len(list(self.media_dir.iterdir())),1)
    def test_unapproved_url_and_bad_file_cannot_enter(self):
        with MediaInbox(self.db_path,self.media_dir) as inbox:
            with self.assertRaises(MediaInboxError):inbox.save_upload(io.BytesIO(b'123'),'clip.mp4',URL)
            with self.assertRaises(MediaInboxError):inbox.save_upload(io.BytesIO(image_bytes()),'clip.png','http://127.0.0.1/private')
            with self.assertRaises(MediaInboxError):inbox.save_upload(io.BytesIO(image_bytes()),'../../evil.png',URL)
            self.assertEqual(inbox.list_tasks(),[])
    def test_failed_worker_preserves_error_and_queued_files(self):
        class Broken:
            def ingest(self,*a,**kw):raise RuntimeError('OCR temporary failure')
        with MediaInbox(self.db_path,self.media_dir) as inbox:
            job=inbox.save_upload(io.BytesIO(image_bytes()),'clip.png',URL)
            after=inbox.process_one(job['task_id'],engine=Broken())
            self.assertEqual(after['status'],'failed')
            self.assertIn('temporary failure',after['error'])
            self.assertEqual(inbox.process_one(job['task_id'],engine=StubEngine())['status'],'failed')

class MediaWebAPITests(unittest.TestCase):
    def test_api_accepts_upload_and_protects_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            token='not-real-secure-token-but-enough-123456'
            app=create_app(db_path=str(Path(td)/'db.sqlite'),token=token)
            with TestClient(app) as c:
                hdr={'Authorization':'Bearer '+token}
                res=c.post('/api/intake/media',headers=hdr,data={'url':URL},files={'file':('clip.png',image_bytes(),'image/png')})
                self.assertEqual(res.status_code,202,res.text)
                tid=res.json()['task_id']
                self.assertEqual(c.get('/api/media-tasks/'+tid).status_code,401)
                self.assertIn(c.get('/api/media-tasks/'+tid,headers=hdr).json()['status'],('complete','partial','failed','queued'))
