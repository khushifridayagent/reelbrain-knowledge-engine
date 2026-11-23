"""Optional paid external acquisition (mock tested only, cost and URL safety gated)."""
import tempfile, unittest
from pathlib import Path
import httpx
from reelbrain.acquire_apify import ApifyReelClient,SafeMediaDownloader,AcquisitionError
from reelbrain.contracts import Observation
from reelbrain.store import KnowledgeStore
from reelbrain.engine import LocalPipelineEngine

URL='https://www.instagram.com/reel/Abc321/'
class ApifyTests(unittest.TestCase):
    def test_no_paid_call_without_consent(self):
        def handler(request):raise AssertionError('no network allowed')
        cli=httpx.Client(transport=httpx.MockTransport(handler))
        p=ApifyReelClient('fake-token',client=cli)
        with self.assertRaises(PermissionError):p.inspect(URL,allow_paid=False)
    def test_apify_actor_body_and_verified_permalink(self):
        captured=[]
        def handler(request):
            captured.append(request)
            return httpx.Response(200,json=[{'inputUrl':URL,'shortCode':'Abc321','caption':'Sample description',
                'videoUrl':'https://scontent.xx.fbcdn.net/media.mp4'}])
        cli=httpx.Client(transport=httpx.MockTransport(handler))
        result=ApifyReelClient('not-a-real-secret',client=cli).inspect(URL,allow_paid=True)
        self.assertEqual(result.url,URL)
        self.assertEqual(result.caption,'Sample description')
        self.assertEqual(result.media_url,'https://scontent.xx.fbcdn.net/media.mp4')
        self.assertIn('api.apify.com',str(captured[0].url))
        self.assertIn(URL,captured[0].content.decode())
        self.assertNotIn('not-a-real-secret',str(captured[0].url))
    def test_actor_mismatched_url_not_attested(self):
        cli=httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=[{'shortCode':'BAD1','videoUrl':'https://x.fbcdn.net/a.mp4'}])))
        with self.assertRaises(AcquisitionError):ApifyReelClient('token',client=cli).inspect(URL,allow_paid=True)
    def test_downloader_rejects_ssrf_and_redirect_without_request(self):
        called=[]
        def handler(request):called.append(request);return httpx.Response(302,headers={'location':'http://169.254.169.254/latest/meta-data'})
        cli=httpx.Client(transport=httpx.MockTransport(handler))
        with tempfile.TemporaryDirectory() as td:
            dl=SafeMediaDownloader(client=cli)
            with self.assertRaises(AcquisitionError):dl.download('http://127.0.0.1/secret',Path(td)/'x.mp4')
            self.assertEqual(called,[])
            with self.assertRaises(AcquisitionError):dl.download('https://video.fbcdn.net/media.mp4',Path(td)/'x.mp4')
            self.assertEqual(len(called),1)
    def test_external_caption_is_separately_provenance_labeled(self):
        # Text originating from a named provider can support claims, but model-inferred
        # observations must NOT become primary source proof.
        with tempfile.TemporaryDirectory() as td:
            from PIL import Image
            Image.new('RGB',(30,30),'white').save(Path(td)/'sample.png')
            db=KnowledgeStore(Path(td)/'db.sqlite')
            try:
                saved=LocalPipelineEngine(db,ocr=lambda p:[]).ingest(
                    Path(td)/'sample.png',URL,extra_observations=[Observation('GitHub https://github.com/onyx-dot-app/onyx',kind='caption',locator='apify:caption')])
                self.assertEqual(saved['resource_count'],1)
                self.assertTrue(saved['processing_receipt_id'])
            finally:db.close()
