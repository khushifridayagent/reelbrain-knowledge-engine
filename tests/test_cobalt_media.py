"""Local-only Cobalt contract; no external calls in unit tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from reelbrain.public_media import PublicMediaError
from reelbrain.cobalt_media import acquire_cobalt_reel, cobalt_ready, validate_cobalt_response

SRC='https://www.instagram.com/reel/DgGHCjZIZtW/'
CDN='https://scontent.cdninstagram.com/example.mp4'
TUNNEL='http://127.0.0.1:9000/tunnel?id=fixture'

class CobaltTests(unittest.TestCase):
    def test_only_local_tunnel_or_instagram_https_cdn(self):
        self.assertEqual(validate_cobalt_response({'status':'redirect','url':CDN}),CDN)
        self.assertEqual(validate_cobalt_response({'status':'tunnel','url':TUNNEL}),TUNNEL)
        for reply in [
            {'status':'redirect','url':'https://example.org/video.mp4'},
            {'status':'tunnel','url':'http://127.0.0.1:9001/tunnel'},
            {'status':'tunnel','url':'http://127.0.0.1:9000/secret'},
            {'status':'redirect','url':'https://user:password@cdninstagram.com/v.mp4'},
            {'status':'picker','picker':[{'type':'photo','url':CDN}]},
            {'status':'error','error':{'code':'private_content'}}]:
            with self.subTest(reply=reply):
                with self.assertRaises(PublicMediaError):validate_cobalt_response(reply)

    def test_not_enabled_without_runner_readiness(self):
        with patch.dict('os.environ',{},clear=True):self.assertFalse(cobalt_ready(SRC))
        with patch.dict('os.environ',{'REELBRAIN_COBALT_READY':'1'},clear=True):
            self.assertTrue(cobalt_ready(SRC))
            self.assertFalse(cobalt_ready('https://www.instagram.com/p/DgGHCjZIZtW/'))

    def test_decoded_video_is_required_and_bad_download_removed(self):
        class Reply:
            status_code=200
            headers={}
            def json(self):return {'status':'redirect','url':CDN}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def iter_bytes(self,chunk_size=1024):yield b'\x00\x00\x00\x18ftypisom'+b'X'*100
        class Client:
            def post(self,url,**kwargs):
                self.url=url;self.body=kwargs['json'];return Reply()
            def stream(self,*args,**kwargs):return Reply()
        def verified(argv,**kw):
            return SimpleNamespace(returncode=0,stdout=json.dumps({
                'streams':[{'width':720,'height':1280}],
                'format':{'duration':'10.0'}}))
        with tempfile.TemporaryDirectory() as d:
            c=Client()
            bundle=acquire_cobalt_reel(SRC,d,http=c,runner=verified)
            self.assertEqual(c.url,'http://127.0.0.1:9000/')
            self.assertEqual(c.body['url'],SRC)
            self.assertEqual(bundle.provider,'cobalt-self-hosted-public')
            self.assertEqual(len(bundle.paths),1)
            self.assertTrue(bundle.paths[0].is_file())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(PublicMediaError):
                acquire_cobalt_reel(SRC,d,http=Client(),
                    runner=lambda *a,**k:SimpleNamespace(returncode=1,stdout=''))
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_workflow_ready_output_routes_real_worker_to_cobalt(self):
        from reelbrain.scrapecreators_media import acquire_with_public_provider
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/reelbrain-media-batch.yml').read_text()
        startup=workflow.split('- name: Start private ephemeral open-source Cobalt',1)[1].split('\n      - ',1)[0]
        import re
        value=re.findall(r'echo "ready=([^"]+)"',startup)[-1]
        self.assertEqual(value,'true')
        with patch.dict('os.environ',{'REELBRAIN_COBALT_READY':value},clear=True):
            self.assertTrue(cobalt_ready(SRC))
            with patch('reelbrain.cobalt_media.acquire_cobalt_reel',return_value='actual-bundle'):
                self.assertEqual(acquire_with_public_provider(SRC,'unused',None),'actual-bundle')

    def test_false_readiness_values_do_not_enable_download(self):
        for value in ('false','0','','unexpected'):
            with patch.dict('os.environ',{'REELBRAIN_COBALT_READY':value},clear=True):
                self.assertFalse(cobalt_ready(SRC))
