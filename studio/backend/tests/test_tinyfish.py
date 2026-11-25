import unittest, os, httpx
from unittest.mock import patch
from studio.research import Research
class TinyFishTests(unittest.TestCase):
    def test_search_fetch_actual_content_and_cache(self):
        requests=[]
        def handler(req):
            requests.append(req)
            if req.url.host=='api.github.com':return httpx.Response(200,json={'items':[]})
            self.assertEqual(req.headers.get('x-api-key'),'fixture-key')
            if req.url.host=='api.search.tinyfish.ai':return httpx.Response(200,json={'results':[{'url':'https://docs.example.com/install','title':'Official documentation','snippet':'Install tool'}]})
            self.assertEqual(req.url.host,'api.fetch.tinyfish.ai')
            return httpx.Response(200,json={'results':[{'url':'https://docs.example.com/install','title':'Install','text':'Actual documented installation instructions and requirements'}],'errors':[]})
        with patch.dict(os.environ,{'TINYFISH_CHATBOT_API_KEY':'fixture-key','STUDIO_WEB_SEARCH_APPROVED':'1'}):
            r=Research(httpx.Client(transport=httpx.MockTransport(handler)))
            a=r.run('example tool installation');b=r.run('example tool installation')
            self.assertTrue(any(x['kind']=='web_page_excerpt' and 'Actual documented' in x['text'] for x in a['documents']))
            self.assertEqual(sum(x.url.host=='api.fetch.tinyfish.ai' for x in requests),1)
            self.assertEqual(sum(x.url.host=='api.search.tinyfish.ai' for x in requests),len(set(str(x.url) for x in requests if x.url.host=='api.search.tinyfish.ai')))
    def test_no_false_page_success(self):
        def handler(req):
            if req.url.host=='api.github.com':return httpx.Response(200,json={'items':[]})
            if req.url.host=='api.search.tinyfish.ai':return httpx.Response(200,json={'results':[{'url':'https://docs.example.com/install','title':'Docs','snippet':'Only search snippet'}]})
            return httpx.Response(200,json={'results':[],'errors':[{'url':'https://docs.example.com/install','error':'timeout'}]})
        with patch.dict(os.environ,{'TINYFISH_CHATBOT_API_KEY':'fixture-key','STUDIO_WEB_SEARCH_APPROVED':'1'}):
            a=Research(httpx.Client(transport=httpx.MockTransport(handler))).run('example tool')
            self.assertFalse(any(x['kind']=='web_page_excerpt' for x in a['documents']))
            self.assertTrue(a['warnings'])
