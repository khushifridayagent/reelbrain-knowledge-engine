"""RED/GREEN tests: ingestion must advance a pending Reel without fabricating video proof."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from reelbrain.pipeline import KnowledgePipeline
from reelbrain.engine import LocalPipelineEngine
from reelbrain.contracts import Observation
from reelbrain.store import KnowledgeStore

class MediaLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=KnowledgeStore(self.root/'test.db')
        self.url='https://www.instagram.com/reel/abc_123/'
        self.pipeline=KnowledgePipeline(self.db)
        self.pipeline.ingest_reel_conversation('chat.md',f'Context: see {self.url}', 'owner')
        self.media=self.root/'clip.mp4'
        self.media.write_bytes(b'FAKE-FIXTURE: expected OCR provider injection; not a real Reel!')
    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def test_successful_media_processing_transitions_link_job_and_preserves_receipt(self):
        engine=LocalPipelineEngine(self.db,ocr=lambda p:[Observation('https://github.com/example/one',kind='ocr',locator='00:02')])
        result=engine.ingest(self.media,self.url,'owner')
        self.assertEqual(result['stage_errors'],{})
        self.assertEqual(self.db.pending_reels('owner'),[])
        job=self.db.con.execute('SELECT status FROM jobs WHERE tenant=?',('owner',)).fetchone()
        self.assertEqual(job['status'],'done')
        history=self.db.processing_history(self.url,'owner')
        self.assertEqual(len(history),1)
        self.assertEqual(history[0]['result_source_id'],result['source_id'])
        self.assertEqual(history[0]['media_sha256'],hashlib.sha256(self.media.read_bytes()).hexdigest())
        self.assertEqual(len(self.db.context_for_reel(self.url,'owner')),1)
        self.assertEqual(self.db.search('example','owner')[0]['status'],'seen')

    def test_no_observations_keeps_pending_and_flags_incomplete(self):
        engine=LocalPipelineEngine(self.db,ocr=lambda p:[])
        result=engine.ingest(self.media,self.url,'owner')
        self.assertEqual(result['status'],'partial')
        self.assertIn('all_passes',result['stage_errors'])
        self.assertEqual(len(self.db.pending_reels('owner')),1)
        self.assertEqual(self.db.processing_history(self.url,'owner'),[])

    def test_one_pass_failure_preserves_available_evidence_as_partial(self):
        class FailingVideo:
            def analyze(self,path):raise RuntimeError('offline')
        engine=LocalPipelineEngine(self.db,ocr=lambda p:[Observation('github.com/example/repo',kind='ocr',locator='00:01')],video_model=FailingVideo())
        result=engine.ingest(self.media,self.url,'owner',allow_external=True)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(self.db.pending_reels('owner')),1)
        self.assertEqual(self.db.pending_reels('owner')[0]['pending_job_status'],'partial')
        self.assertEqual(self.db.processing_history(self.url,'owner')[0]['status'],'partial')
        self.assertEqual(len(self.db.search('repo','owner')),1)

    def test_second_processing_is_idempotent(self):
        engine=LocalPipelineEngine(self.db,ocr=lambda p:[Observation('github.com/example/one',kind='ocr',locator='00:02')])
        engine.ingest(self.media,self.url,'owner');engine.ingest(self.media,self.url,'owner')
        self.assertEqual(len(self.db.processing_history(self.url,'owner')),1)

if __name__=='__main__':unittest.main()
