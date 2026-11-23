"""Visually demonstrable but text-free media should yield labeled partial inference."""
import tempfile,unittest
from pathlib import Path
from reelbrain.contracts import Observation
from reelbrain.store import KnowledgeStore

class OnlyVisualModel:
    def analyze(self,p):
        return [Observation('The camera shows a physical craft being assembled',kind='model_inference',locator='00:02')]

class VisualInferenceTests(unittest.TestCase):
    def test_visual_only_media_is_partial_and_model_claim_does_not_become_verified_resource(self):
        from reelbrain.engine import LocalPipelineEngine
        with tempfile.TemporaryDirectory() as d:
            store=KnowledgeStore(Path(d)/'db.sqlite')
            try:
                media=Path(d)/'example.mp4';media.write_bytes(b'example-bytes-with-model-stub')
                result=LocalPipelineEngine(store,ocr=lambda _:[],video_model=OnlyVisualModel()).ingest(
                    media,'https://www.instagram.com/reel/ExampleReel1/',allow_external=True)
                self.assertEqual(result['status'],'partial')
                self.assertTrue(result.get('processing_receipt_id'))
                self.assertEqual(result['resource_count'],0)
                self.assertIn('no_source_evidence',result['stage_errors'])
            finally:store.close()
if __name__=='__main__':unittest.main()
