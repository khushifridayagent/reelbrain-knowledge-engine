"""Carousel visual inferences from earlier slides survive later model quota."""
import tempfile, unittest
from pathlib import Path
import numpy as np
import cv2

class ThreePageModel:
    requires_external=True
    def __init__(self):self.count=0
    def analyze(self,path):
        from reelbrain.qwen_vl import QwenPartialVisualError
        from reelbrain.contracts import Observation
        self.count+=1
        if self.count==3:
            raise QwenPartialVisualError('quota exceeded',[])
        return [Observation('A workflow arrow leads from input to output at page '+str(self.count),
                           kind='model_inference',locator='qwen3-vl:image:01')]

class SlideRetentionTests(unittest.TestCase):
    def test_keep_first_two_pages_when_third_hits_cloudflare_free_quota(self):
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.contracts import Observation
        from reelbrain.store import KnowledgeStore
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            files=[]
            for page in range(1,6):
                path=root/f'page_{page}.png'
                cv2.imwrite(str(path),np.full((400,600,3),255,np.uint8))
                files.append(path)
            store=KnowledgeStore(root/'evidence.sqlite')
            try:
                result=LocalPipelineEngine(
                    store,ocr=lambda _: [Observation('Visible: input -> output',
                                                   kind='ocr',locator='image:1')],
                    video_model=ThreePageModel()).ingest(
                    files,'https://www.instagram.com/p/DgGHCjZIZtW/',
                    allow_external=True)
                self.assertEqual(result['status'],'partial')
                self.assertEqual(result['stage_observations']['vlm'],2)
                self.assertIn('quota',result['stage_errors']['vlm'])
                observations=store.con.execute(
                    "SELECT locator,verbatim FROM evidence WHERE kind='model_inference'"
                ).fetchall()
                self.assertEqual(len(observations),2)
                self.assertTrue(any('slide:01' in row['locator'] for row in observations))
                self.assertTrue(any('slide:02' in row['locator'] for row in observations))
                self.assertTrue(all('workflow arrow' in row['verbatim'] for row in observations))
            finally:store.close()

if __name__=='__main__':unittest.main()
