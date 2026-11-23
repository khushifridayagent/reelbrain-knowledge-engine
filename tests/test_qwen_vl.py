"""Self-hosted Qwen3-VL requests stay model-inference, never source proof."""
import json, tempfile, unittest
from pathlib import Path

class FakeResponse:
    def raise_for_status(self):pass
    def json(self):
        return {'choices':[{'message':{'content':json.dumps({'observations':[
            {'timestamp':'00:01','description':'Screenshot shows installation commands'}]})}}]}
class FakeClient:
    def post(self,url,**kw):
        self.url=url;self.kw=kw
        return FakeResponse()
class QwenTests(unittest.TestCase):
    def test_image_inference_is_typed_and_sent_only_to_configured_endpoint(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'slide.png';Image.new('RGB',(200,100),'white').save(p)
            client=FakeClient()
            result=QwenVLResearcher('https://example-ml.host/v1',
                       api_key='fixture',client=client).analyze(p)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0].kind,'model_inference')
            self.assertIn('chat/completions',client.url)
            self.assertEqual(client.kw['json']['model'],'Qwen/Qwen3-VL-8B-Instruct')
            self.assertTrue(any(i['type']=='image_url' for i in client.kw['json']['messages'][0]['content']))
    def test_local_http_host_permitted_but_public_insecure_host_forbidden(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with self.assertRaises(ValueError):
            QwenVLResearcher('http://example-ml.host/v1',client=FakeClient())
        QwenVLResearcher('http://127.0.0.1:8000/v1',client=FakeClient())
if __name__=='__main__':unittest.main()
