import unittest,os,json,httpx
from unittest.mock import patch
from studio.llm import LLM
class FallbackTests(unittest.TestCase):
    def test_groq_rate_limit_falls_back_to_gemini(self):
        seen=[]
        def handler(req):
            seen.append(req.url.host)
            if req.url.host=='api.groq.com':
                self.assertEqual(req.headers['Authorization'],'Bearer groq-fixture')
                return httpx.Response(429,headers={'Retry-After':'60'})
            self.assertEqual(req.headers['x-goog-api-key'],'gemini-fixture')
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}]})
        with patch.dict(os.environ,{'STUDIO_EXTERNAL_LLM_APPROVED':'1','GROQ_CHATBOT_API_KEY':'groq-fixture','GEMINI_CHATBOT_API_KEY':'gemini-fixture'}):
            llm=LLM(httpx.Client(transport=httpx.MockTransport(handler)))
            self.assertEqual(llm.call('Return JSON',{'question':'public fixture'}),{'ok':True})
            self.assertEqual(llm.call('Return JSON',{'question':'public fixture 2'}),{'ok':True})
        self.assertEqual(seen,['api.groq.com','generativelanguage.googleapis.com','generativelanguage.googleapis.com'])
    def test_extraction_credentials_are_never_fallback_keys(self):
        with patch.dict(os.environ,{'STUDIO_EXTERNAL_LLM_APPROVED':'1','GROQ_API_KEY':'old','GEMINI_API_KEY':'old'},clear=True):
            llm=LLM(httpx.Client(transport=httpx.MockTransport(lambda r:self.fail('must not call provider'))))
            self.assertIsNone(llm.call('Return JSON',{'question':'fixture'}))
