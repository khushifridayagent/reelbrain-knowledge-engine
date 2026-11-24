import unittest
from threading import Barrier, Event
from pathlib import Path
from reelbrain.resumable_media import drain_overlapping, retry_seconds, classify_model_http, stage_slot

class ResumableMediaTests(unittest.TestCase):
    def test_two_jobs_overlap_without_shared_connection(self):
        barrier=Barrier(2,timeout=3)
        def worker(config,batch_size=1):
            barrier.wait()
            return [{'status':'processed'}]
        result=drain_overlapping({},max_jobs=2,process_batch=worker,time_remaining=lambda:10000)
        self.assertEqual(len(result),2)
    def test_partial_visual_not_terminal(self):
        self.assertEqual(retry_seconds({'vlm':'visual model request failed'}),3600)
        self.assertIsNone(retry_seconds({}))
        self.assertEqual(classify_model_http(429),'quota exceeded')
        self.assertEqual(classify_model_http(503),'service unavailable')
        self.assertEqual(classify_model_http(400),'visual request rejected HTTP 400')
    def test_no_fourteen_minute_workflow_kill(self):
        path=Path(__file__).resolve().parents[1]/'.github/workflows/reelbrain-media-batch.yml'
        text=path.read_text()
        self.assertNotIn('timeout-minutes: 14',text)
        self.assertIn('drain_overlapping(',text)
        self.assertIn('cancel-in-progress: false',text)

    def test_download_overlaps_analysis_and_storage_is_separate(self):
        first_analysis=Event()
        second_download=Event()
        second_analysis=Event()
        first_storage=Event()
        from threading import Lock
        lock=Lock()
        counter=[0]
        def worker(config,batch_size=1):
            with lock:
                counter[0]+=1
                job=counter[0]
            if job==2:
                self.assertTrue(first_analysis.wait(3))
            with stage_slot('download'):
                if job==2:
                    second_download.set()
            with stage_slot('analysis'):
                if job==1:
                    first_analysis.set()
                    self.assertTrue(second_download.wait(3))
                else:
                    second_analysis.set()
                    self.assertTrue(first_storage.wait(3))
            with stage_slot('storage'):
                if job==1:
                    first_storage.set()
                    self.assertTrue(second_analysis.wait(3))
            return [{'id':job,'status':'processed'}]
        result=drain_overlapping({},max_jobs=2,process_batch=worker,time_remaining=lambda:10000)
        self.assertEqual({x['id'] for x in result},{1,2})

    def test_checkpoint_reuses_completed_pass_not_failed_pass(self):
        from tempfile import TemporaryDirectory
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.store import KnowledgeStore
        from reelbrain.contracts import Observation
        from unittest.mock import Mock
        class Cache:
            def __init__(self):self.data={}
            def load(self,stage):return self.data.get(stage)
            def save(self,stage,events,elapsed):self.data[stage]=(events,elapsed)
        cache=Cache()
        ocr=Mock(return_value=[Observation('Exact visible text',kind='ocr',locator='00:01')])
        vision=Mock()
        vision.requires_external=False
        vision.analyze.side_effect=[RuntimeError('unavailable'),[Observation('Visual details',kind='model_inference',locator='00:01')]]
        with TemporaryDirectory() as d:
            p=Path(d)/'sample.png'
            p.write_bytes(b'fixture')
            db=KnowledgeStore(Path(d)/'evidence.sqlite')
            try:
                engine=LocalPipelineEngine(db,ocr=ocr,video_model=vision)
                url='https://www.instagram.com/reel/ABC123/'
                first=engine.ingest(p,url,checkpoint=cache)
                second=engine.ingest(p,url,checkpoint=cache)
                self.assertEqual(first['status'],'partial')
                self.assertEqual(second['status'],'evidence_saved')
                self.assertEqual(ocr.call_count,1)
                self.assertEqual(vision.analyze.call_count,2)
            finally:db.close()
