import unittest,os,base64
from unittest.mock import patch
import httpx
from studio.research import Research,read_public_page
class ResearchTests(unittest.TestCase):
    def test_private_dns_rejected_before_socket(self):
        with patch('studio.research.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('studio.research._PinnedHTTPS') as conn:
            with self.assertRaises(ValueError):read_public_page('https://docs.example.com/')
            conn.assert_not_called()
    def test_github_exact_repo_metadata_and_readme(self):
        def handler(req):
            self.assertEqual(req.url.host,'api.github.com')
            if req.url.path.endswith('/readme'):return httpx.Response(200,json={'encoding':'base64','content':base64.b64encode(b'Installation workflow and setup').decode(),'html_url':'https://github.com/owner/tool/blob/main/README.md'})
            return httpx.Response(200,json={'full_name':'owner/tool','private':False,'description':'Tool'})
        with patch.dict(os.environ,{'GH_CHATBOT_TOKEN':'','STUDIO_WEB_SEARCH_APPROVED':'0'}):
            r=Research(httpx.Client(transport=httpx.MockTransport(handler))).run('tool docs',['https://github.com/owner/tool'])
            self.assertEqual([d['kind'] for d in r['documents']],['github_metadata','github_readme'])
    def test_private_repo_not_disclosed(self):
        client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'full_name':'owner/tool','private':True})))
        with patch.dict(os.environ,{'GH_CHATBOT_TOKEN':'','STUDIO_WEB_SEARCH_APPROVED':'0'}):
            self.assertEqual(Research(client).run('tool docs',['https://github.com/owner/tool'])['documents'],[])
