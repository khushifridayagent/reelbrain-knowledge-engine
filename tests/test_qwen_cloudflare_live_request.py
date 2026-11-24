"""Production Cloudflare Qwen vision API must not waste entire Neuron quota on
default xhigh reasoning and return null message.content."""
import tempfile,unittest
from pathlib import Path
from PIL import Image


class Reply:
    status_code=200
    def raise_for_status(self):pass
    def json(self):
        return {'choices':[{'message':{'content':'{"observations":[{"timestamp":"frame:0","description":"Visible pipeline: INPUT then FILTER then OUTPUT."}]}'}}]}


class HTTP:
    def __init__(self):self.body=None
    def post(self,url,**kwargs):self.body=kwargs['json'];return Reply()


class QwenCloudflareRequestTests(unittest.TestCase):
    def test_cloudflare_uses_low_reasoning_structured_json_and_completion_limit(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'diagram.png'
            Image.new('RGB',(320,170),'white').save(p)
            client=HTTP()
            model=QwenVLResearcher(
              'https://api.cloudflare.com/client/v4/accounts/02b03be7b36836e4f1c84ea80cd3c596/ai/v1',
              model='@cf/qwen/qwen3.8-27b',api_key='fixture',client=client,max_frames=4)
            result=model.analyze(p)
            self.assertEqual(len(result),1)
            self.assertEqual(result[0].kind,'model_inference')
            body=client.body
            self.assertEqual(body['reasoning_effort'],'low')
            self.assertEqual(body['response_format'],{'type':'json_object'})
            self.assertGreaterEqual(body['max_completion_tokens'],800)
            self.assertNotIn('enable_thinking',body)

    def test_non_cloudflare_endpoint_stays_backwards_compatible(self):
        from reelbrain.qwen_vl import QwenVLResearcher
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'poster.png'
            Image.new('RGB',(200,100),'white').save(p)
            c=HTTP()
            QwenVLResearcher('https://custom-qwen.example/v1',
              model='Qwen/Qwen3-VL-8B-Instruct',client=c).analyze(p)
            self.assertNotIn('reasoning_effort',c.body)
            self.assertNotIn('response_format',c.body)

if __name__=='__main__':unittest.main()
