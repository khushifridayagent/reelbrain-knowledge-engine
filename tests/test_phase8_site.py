import os,unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from reelbrain_site.app import app
class SiteTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def test_defaults_fail_closed_without_config(self):
        with patch.dict(os.environ,{'REELBRAIN_DASHBOARD_TOKEN':''}):
            self.assertEqual(self.client.get('/api/search',params={'q':'onyx'}).status_code,503)
    def test_html_has_no_secrets_and_access_bearer(self):
        r=self.client.get('/');self.assertEqual(r.status_code,200)
        self.assertIn('Search my research',r.text);self.assertNotIn('SUPABASE_SERVICE_ROLE_KEY',r.text)
        with patch.dict(os.environ,{'REELBRAIN_DASHBOARD_TOKEN':'x'*40}):
            self.assertEqual(self.client.get('/api/search',params={'q':'onyx'}).status_code,401)
    def test_online_details_does_not_use_database(self):
        with patch.dict(os.environ,{'REELBRAIN_DASHBOARD_TOKEN':'x'*40}):
            with patch('reelbrain_site.app.query_db',side_effect=AssertionError('online details must not touch core DB')):
                r=self.client.get('/api/details',params={'url':'https://example.com'},headers={'Authorization':'Bearer '+'x'*40})
        self.assertEqual(r.status_code,422)
    def test_intake_canonicalizes_and_uses_durable_postgres(self):
        with patch.dict(os.environ,{'REELBRAIN_DASHBOARD_TOKEN':'x'*40}):
            with patch('reelbrain_site.app.query_db',return_value=[{'id':1,'status':'queued','source_url':'https://www.instagram.com/reel/ABC123/'}]) as q:
                r=self.client.post('/api/intake',json={'url':'https://instagram.com/reel/ABC123/?igsh=hi'},headers={'Authorization':'Bearer '+'x'*40})
        self.assertEqual(r.status_code,202);self.assertIn('queued',r.text);self.assertEqual(q.call_args.args[1][0],'https://www.instagram.com/reel/ABC123/')
if __name__=='__main__':unittest.main()
