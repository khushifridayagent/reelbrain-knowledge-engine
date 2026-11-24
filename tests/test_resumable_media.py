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
            with stage_slot('download'):
                if job==2:
                    self.assertTrue(first_analysis.wait(3))
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
