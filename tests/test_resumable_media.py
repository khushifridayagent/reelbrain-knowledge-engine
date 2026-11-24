import unittest
from threading import Barrier
from pathlib import Path
from reelbrain.resumable_media import drain_overlapping, retry_seconds, storage_allowed, classify_model_http

class ResumableMediaTests(unittest.TestCase):
    def test_two_jobs_overlap_without_shared_connection(self):
        barrier=Barrier(2,timeout=3)
        def worker(config,batch_size=1):
            barrier.wait()
            return [{'status':'processed'}]
        result=drain_overlapping({},max_jobs=2,process_batch=worker,time_remaining=lambda:10000)
        self.assertEqual(len(result),2)
    def test_storage_limit_reserves_headroom(self):
        self.assertTrue(storage_allowed(200_000_000))
        self.assertFalse(storage_allowed(295_000_000))
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
