"""Token-free regression tests for Meta Graph production probes.

Never execute real API requests in CI unit tests. Integration GitHub workflow
uses the user's existing protected Actions secret, prints only safe categories.
"""
import unittest
from reelbrain.meta_graph_probe import classify_graph_failure, check_meta_business_access

class FakeResponse:
    def __init__(self,status,body):
        self.status_code=status;self._body=body
    def json(self):return self._body

class FakeHttp:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return self.responses.pop(0)

class GraphProbeTests(unittest.TestCase):
    def test_expired_token_safe_code_190(self):
        self.assertEqual(classify_graph_failure({'error':{'code':190,'message':'token should NOT be logged'}}),'token_expired_or_invalid')
    def test_app_request_limit_safe_code_4(self):
        self.assertEqual(classify_graph_failure({'error':{'code':4,'message':'private details'}}),'app_rate_limited')
    def test_permissions_code_10(self):
        self.assertEqual(classify_graph_failure({'error':{'code':10,'message':'private details'}}),'insufficient_graph_permissions')
    def test_only_fetch_when_token_numeric_id_and_optin_present(self):
        http=FakeHttp([])
        self.assertEqual(check_meta_business_access('', '17841400001234567','1',http=http)['status'],'missing_token')
        self.assertEqual(check_meta_business_access('fixture','notid','1',http=http)['status'],'invalid_ig_user_id')
        self.assertEqual(check_meta_business_access('fixture','17841400001234567','0',http=http)['status'],'disabled')
        self.assertEqual(http.calls,[])
    def test_response_with_reel_but_no_original_media_is_not_success(self):
        http=FakeHttp([
          FakeResponse(200,{'id':'123'}),
          FakeResponse(200,{'id':'17841400001234567','username':'ownbusiness'}),
          FakeResponse(200,{'business_discovery':{'username':'aimortal.ig','media':{'data':[
            {'permalink':'https://www.instagram.com/reel/DgGHCjZIZtW/',
             'media_type':'VIDEO'}
          ]}}})
        ])
        r=check_meta_business_access('fixture','17841400001234567','1',
                                     creator='aimortal.ig',shortcode='DgGHCjZIZtW',http=http)
        self.assertEqual(r['status'],'media_found_without_original_url')
        self.assertEqual(r['matched_media'],1)
        self.assertEqual(r['original_urls'],0)
        self.assertEqual(len(http.calls),3)
        self.assertTrue(all(c['Authorization']=='Bearer fixture' for _,x in http.calls for c in [x['headers']]))
    def test_original_media_url_must_match_validated_meta_cdn(self):
        http=FakeHttp([
          FakeResponse(200,{'id':'123'}),
          FakeResponse(200,{'id':'17841400001234567','username':'ownbusiness'}),
          FakeResponse(200,{'business_discovery':{'username':'aimortal.ig','media':{'data':[
            {'permalink':'https://www.instagram.com/p/DgGHCjZIZtW/',
             'media_type':'VIDEO','media_url':'https://scontent.cdninstagram.com/a.mp4'}
          ]}}})
        ])
        r=check_meta_business_access('fixture','17841400001234567','1',
                                     creator='aimortal.ig',shortcode='DgGHCjZIZtW',http=http)
        self.assertEqual(r['status'],'original_media_url_available')
        self.assertEqual(r['original_urls'],1)
        self.assertNotIn('scontent.cdninstagram.com',str(r))
    def test_errors_never_disclose_token_or_graph_message(self):
        http=FakeHttp([FakeResponse(400,{'error':{'code':190,'message':'raw Bearer fixture'}})])
        r=check_meta_business_access('fixture','17841400001234567','1',http=http)
        self.assertEqual(r['status'],'token_expired_or_invalid')
        self.assertNotIn('fixture',str(r))
        self.assertNotIn('Bearer',str(r))
    def test_source_identity_cannot_be_substituted(self):
        http=FakeHttp([
          FakeResponse(200,{'id':'123'}),
          FakeResponse(200,{'id':'17841400001234567','username':'ownbusiness'}),
          FakeResponse(200,{'business_discovery':{'username':'aimortal.ig','media':{'data':[
            {'permalink':'https://www.instagram.com/reel/WRONGSHORT/',
             'media_type':'VIDEO','media_url':'https://scontent.cdninstagram.com/a.mp4'}
          ]}}})
        ])
        r=check_meta_business_access('fixture','17841400001234567','1',creator='aimortal.ig',shortcode='DgGHCjZIZtW',http=http)
        self.assertEqual(r['status'],'source_not_in_business_discovery')
if __name__=='__main__':unittest.main()
