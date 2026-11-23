"""Official *1:1 professional inbox* webhook, not Instagram Techies group capture."""
import hmac, hashlib, json, os, tempfile, unittest
from pathlib import Path
from fastapi.testclient import TestClient
from reelbrain.webapp import create_app

class MetaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.path=Path(self.tmp.name)/'db.sqlite'
        self.secret='different-app-secret-with-padding-333333';self.verify='my-verify-token-01234567890'
        self.client=TestClient(create_app(db_path=self.path,token='private-test-api-token-12345678901234567890',
                                          meta_app_secret=self.secret,meta_verify_token=self.verify,
                                          meta_receiver_id='business999',meta_allowed_senders={'myOne','myTwo','myThree'}))
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def signed(self,data):
        raw=json.dumps(data,separators=(',',':')).encode()
        sig='sha256='+hmac.new(self.secret.encode(),raw,hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/instagram',content=raw,headers={'X-Hub-Signature-256':sig,'Content-Type':'application/json'})
    def event(self,sender='myOne',mid='message1',txt='https://instagram.com/reel/Test111/',echo=False):
        return {'object':'instagram','entry':[{'id':'business999','messaging':[{'sender':{'id':sender},
             'recipient':{'id':'business999'},'message':{'mid':mid,'text':txt,'is_echo':echo}}]}]}
    def test_verification_get_challenge_and_reject_invalid(self):
        r=self.client.get('/webhooks/instagram',params={'hub.mode':'subscribe','hub.verify_token':self.verify,'hub.challenge':'4811'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.text,'4811')
        self.assertEqual(self.client.get('/webhooks/instagram',params={'hub.mode':'subscribe','hub.verify_token':'wrong','hub.challenge':'4811'}).status_code,403)
    def test_bad_signature_rejected_without_write(self):
        r=self.client.post('/webhooks/instagram',json=self.event());self.assertEqual(r.status_code,403)
        self.assertEqual(self.client.get('/api/pending',headers={'Authorization':'Bearer private-test-api-token-12345678901234567890'}).json()['items'],[])
    def test_signed_authorized_1to1_reel_share_only(self):
        result=self.signed(self.event());self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['saved_links'],1)
        self.assertEqual(self.signed(self.event()).json()['saved_links'],0)
        self.assertEqual(len(self.client.get('/api/pending',headers={'Authorization':'Bearer private-test-api-token-12345678901234567890'}).json()['items']),1)
    def test_skip_unknown_senders_echoes_and_third_party_urls(self):
        self.assertEqual(self.signed(self.event(sender='stranger',mid='2')).json()['saved_links'],0)
        self.assertEqual(self.signed(self.event(sender='myOne',mid='3',echo=True)).json()['saved_links'],0)
        self.assertEqual(self.signed(self.event(sender='myOne',mid='4',txt='https://private.evil.test/')).json()['saved_links'],0)
    def test_signed_ig_reel_attachment(self):
        data=self.event(mid='abc2',txt='')
        data['entry'][0]['messaging'][0]['message']['attachments']=[{'type':'ig_reel','payload':{'url':'https://www.instagram.com/reel/New77/'}}]
        self.assertEqual(self.signed(data).json()['saved_links'],1)
