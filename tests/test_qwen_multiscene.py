"""Advanced visual evidence: scene-aware batching and partial quota persistence."""
import json, tempfile, unittest
from pathlib import Path
import cv2
import numpy as np


class FakeResponse:
    status_code=200
    def raise_for_status(self):return None
    def json(self):
        return {'choices':[{'message':{'content':json.dumps({'observations':[
           {'timestamp':'frame:0','description':'User opens an AI workflow dashboard and configures a model.'}]})}}]}


class BatchClient:
    def __init__(self,fail_after=None):
        self.requests=[];self.fail_after=fail_after
    def post(self,url,**kwargs):
        self.requests.append(kwargs)
        if self.fail_after and len(self.requests)>self.fail_after:
            return type('Err',(),{'status_code':429,'raise_for_status':lambda self:(_ for _ in ()).throw(RuntimeError('quota')),})()
        return FakeResponse()


def video_with_scenes(path,scenes=12):
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),4,(640,360))
    if not writer.isOpened():return False
    for scene in range(scenes):
        for _ in range(4):
            frame=np.full((360,640,3),255,np.uint8)
            # Large changing high-contrast shapes make a reproducible scene
            # transition without requiring an Instagram download or network.
            offset=(scene*37)%450
            cv2.rectangle(frame,(offset+8,30),(offset+125,290),(10,10,10),-1)
            cv2.putText(frame,'STEP '+str(scene+1),(15,320),
                        cv2.FONT_HERSHEY_SIMPLEX,2,(0,0,0),4)
            writer.write(frame)
    writer.release()
    return True


class QwenSceneTests(unittest.TestCase):
    def test_video_uses_more_than_eight_frames_when_visual_states_change(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slides.mp4'
            if not video_with_scenes(p,12):self.skipTest('MP4 encoder unavailable')
            client=BatchClient()
            model=QwenVLResearcher('https://remote.example/v1',client=client,
                                  max_frames=4,max_batches=4)
            result=model.analyze(p)
            self.assertGreater(len(client.requests),1)
            self.assertLessEqual(len(client.requests),4)
            self.assertTrue(result)
            for request in client.requests:
                content=request['json']['messages'][0]['content']
                self.assertLessEqual(sum(item['type']=='image_url' for item in content),4)
            self.assertTrue(all(x.kind=='model_inference' for x in result))
            self.assertTrue(all('qwen' in x.locator for x in result))

    def test_cloudflare_429_returns_previous_valid_scene_evidence_and_error(self):
        from reelbrain.qwen_vl import QwenVLResearcher, QwenPartialVisualError
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slides.mp4'
            if not video_with_scenes(p,12):self.skipTest('MP4 encoder unavailable')
            model=QwenVLResearcher('https://remote.example/v1',
                client=BatchClient(fail_after=1),max_frames=3,max_batches=4)
            with self.assertRaises(QwenPartialVisualError) as context:
                model.analyze(p)
            error=context.exception
            self.assertIn('quota',str(error).lower())
            self.assertGreater(len(error.partial_observations),0)
            self.assertTrue(all(e.kind=='model_inference' for e in error.partial_observations))
            self.assertNotIn('Bearer',str(error))

    def test_single_image_keeps_existing_one_call_behavior(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slide.png'
            cv2.imwrite(str(p),np.full((250,500,3),255,np.uint8))
            client=BatchClient()
            result=QwenVLResearcher('https://remote.example/v1',
                                    client=client,max_frames=4,max_batches=4).analyze(p)
            self.assertEqual(len(client.requests),1)
            self.assertEqual(len(result),1)

    def test_more_than_one_dense_scene_has_traceable_time_locator(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slides.mp4'
            if not video_with_scenes(p,10):self.skipTest('MP4 encoder unavailable')
            client=BatchClient()
            result=QwenVLResearcher('https://remote.example/v1',
                          client=client,max_frames=2,max_batches=4).analyze(p)
            self.assertTrue(all('frame:0' not in ev.locator for ev in result))
            self.assertTrue(any('00:' in ev.locator for ev in result))


if __name__=='__main__':unittest.main()
