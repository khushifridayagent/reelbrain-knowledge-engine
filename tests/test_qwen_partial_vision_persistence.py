"""Do not discard completed VLM frame evidence when a later batch hits quota."""
import tempfile,unittest
from pathlib import Path
import numpy as np
import cv2


class QuotaModel:
    requires_external=True
    def analyze(self,path):
        from reelbrain.qwen_vl import QwenPartialVisualError
        from reelbrain.contracts import Observation
        raise QwenPartialVisualError('quota exceeded',[
          Observation('The dashboard shows a triggered action and two branching nodes.',
                      kind='model_inference',locator='qwen3-vl:00:01.00')
        ])


class VisualQuotaPersistenceTests(unittest.TestCase):
    def test_keep_partial_model_frames_and_ocr_and_queue_retry(self):
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.store import KnowledgeStore
        from reelbrain.contracts import Observation
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            p=root/'visible.png'
            cv2.imwrite(str(p),np.full((300,500,3),255,np.uint8))
            db=KnowledgeStore(root/'evidence.sqlite')
            try:
                engine=LocalPipelineEngine(db,
                    ocr=lambda _:[Observation('github.com/example/workflow',
                                             kind='ocr',locator='image:1')],
                    video_model=QuotaModel())
                result=engine.ingest(p,'https://www.instagram.com/p/DgGHCjZIZtW/',
                                     allow_external=True)
                self.assertEqual(result['status'],'partial')
                self.assertEqual(result['stage_observations']['vlm'],1)
                self.assertIn('quota exceeded',result['stage_errors']['vlm'])
                data=db.con.execute('SELECT kind,locator,verbatim FROM evidence').fetchall()
                self.assertTrue(any(item['kind']=='model_inference' and
                                    'branching nodes' in item['verbatim'] for item in data))
                self.assertTrue(any(item['kind']=='ocr' for item in data))
                from reelbrain.model_quota_retry import model_quota_retry_seconds
                self.assertIsNotNone(model_quota_retry_seconds(result['stage_errors']))
            finally:db.close()


if __name__=='__main__':unittest.main()
