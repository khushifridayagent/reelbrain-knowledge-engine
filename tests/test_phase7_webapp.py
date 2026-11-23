"""Phase 7 — web share intake is gated; link-only never claims media read."""
import tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from reelbrain.webapp import create_app

API_KEY='only-for-testing-1234567890123456'

class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory()
        self.client=TestClient(create_app(db_path=str(Path(self.d.name)/'knowledge.db'),token=API_KEY))
        self.headers={'Authorization':f'Bearer {API_KEY}'}
    def tearDown(self):self.client.close();self.d.cleanup()
    def test_unauthorized_cannot_read_or_write(self):
        self.assertEqual(self.client.get('/api/search',params={'q':'RAG'}).status_code,401)
        self.assertEqual(self.client.post('/api/intake/link',json={'url':'https://instagram.com/reel/Abc1/'}).status_code,401)
        self.assertEqual(self.client.post('/api/intake/link',headers={'Authorization':'Bearer wrong'},json={'url':'https://instagram.com/reel/Abc1/'}).status_code,401)
    def test_link_only_progress_and_dedupe(self):
        url='https://instagram.com/reel/Abc1/?igsh=x'
        a=self.client.post('/api/intake/link',headers=self.headers,json={'url':url})
        self.assertEqual(a.status_code,202,a.text)
        b=self.client.post('/api/intake/link',headers=self.headers,json={'url':url})
        self.assertEqual(b.status_code,202)
        self.assertEqual(a.json()['canonical_url'],b.json()['canonical_url'])
        self.assertEqual(a.json()['status'],'awaiting_authorized_media')
        pending=self.client.get('/api/pending',headers=self.headers)
        self.assertEqual(pending.status_code,200)
        self.assertEqual(len(pending.json()['items']),1)
    def test_no_ssrf_and_no_fake_ig_group_sync(self):
        for url in ('http://127.0.0.1/foo','https://instagram.com.evil.org/reel/A/','file:///etc/passwd'):
            self.assertEqual(self.client.post('/api/intake/link',headers=self.headers,json={'url':url}).status_code,422)
        self.assertEqual(self.client.post('/api/instagram-group-sync',headers=self.headers,json={'group':'Techies'}).status_code,404)
    def test_share_screen_does_not_write_without_auth(self):
        r=self.client.post('/share',data={'text':'https://www.instagram.com/reel/Abc12/'})
        self.assertEqual(r.status_code,200)
        self.assertIn('Abc12',r.text)
        self.assertEqual(self.client.get('/api/pending',headers=self.headers).json()['items'],[])
    def test_pwa_manifest_and_headers(self):
        m=self.client.get('/manifest.webmanifest')
        self.assertEqual(m.status_code,200)
        self.assertIn('share_target',m.json())
        self.assertIn('Content-Security-Policy',self.client.get('/').headers)
