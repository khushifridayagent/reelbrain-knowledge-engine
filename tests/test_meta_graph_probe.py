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
    def test_linked_page_ig_id_is_derived_when_configured_id_is_page_or_app(self):
        from reelbrain.meta_graph_probe import choose_linked_professional_ig_id
        pages={'data':[{'id':'11223344','instagram_business_account':{'id':'17841400001234567'}}]}
        self.assertEqual(choose_linked_professional_ig_id(pages,'1234567890'),
                         '17841400001234567')

    def test_ambiguous_multiple_ig_accounts_must_never_guess(self):
        from reelbrain.meta_graph_probe import choose_linked_professional_ig_id
        pages={'data':[{'instagram_business_account':{'id':'17841400001234567'}},
                       {'instagram_business_account':{'id':'17841400007654321'}}]}
        self.assertIsNone(choose_linked_professional_ig_id(pages,'999999999'))
        self.assertEqual(choose_linked_professional_ig_id(pages,'17841400007654321'),
                         '17841400007654321')

    def test_invalid_id_100_recovers_using_single_linked_professional(self):
        http=FakeHttp([
            FakeResponse(200,{'id':'123'}),
            FakeResponse(400,{'error':{'code':100,'message':'unknown username field'}}),
            FakeResponse(200,{'data':[{'id':'1122','instagram_business_account':{'id':'17841400001234567'}}]}),
            FakeResponse(200,{'id':'17841400001234567','username':'ownbusiness'}),
            FakeResponse(200,{'business_discovery':{'username':'aimortal.ig','media':{'data':[{
                'permalink':'https://www.instagram.com/reel/DgGHCjZIZtW/',
                'media_type':'VIDEO','media_url':'https://scontent.cdninstagram.com/a.mp4'
            }]}}})
        ])
        r=check_meta_business_access('fixture','112233445566','1',http=http)
        self.assertEqual(r['status'],'original_media_url_available')
        self.assertEqual(r['resolved_from_linked_page'],True)
        self.assertNotIn('17841400001234567',str(r))
        self.assertEqual(len(http.calls),5)

    def test_missing_page_access_is_diagnostic_not_token_error(self):
        http=FakeHttp([
            FakeResponse(200,{'id':'123'}),
            FakeResponse(400,{'error':{'code':100,'message':'unsupported field'}}),
            FakeResponse(400,{'error':{'code':10,'message':'lack of pages_show_list'}})
        ])
        r=check_meta_business_access('fixture','112233445566','1',http=http)
        self.assertEqual(r['status'],'linked_page_access_denied')
        self.assertTrue(r['token_valid'])

    def test_report_linked_pages_counts_without_numeric_ids(self):
        http=FakeHttp([
          FakeResponse(200,{'id':'123'}),
          FakeResponse(400,{'error':{'code':100}}),
          FakeResponse(200,{'data':[{'id':'11223344'},
               {'id':'55443322','instagram_business_account':{'id':'17841400001234567'}},
               {'id':'55443323','instagram_business_account':{'id':'17841400007654321'}}]})
        ])
        r=check_meta_business_access('fixture','1234567890','1',http=http)
        self.assertEqual(r['status'],'linked_professional_id_ambiguous_or_missing')
        self.assertEqual(r['visible_facebook_pages'],3)
        self.assertEqual(r['visible_professional_instagram_accounts'],2)
        self.assertNotIn('17841400001234567',str(r))

    def test_inspect_only_granted_scope_flags_without_returning_user_data(self):
        from reelbrain.meta_graph_probe import inspect_graph_permissions
        http=FakeHttp([FakeResponse(200,{'data':[
           {'permission':'instagram_basic','status':'granted'},
           {'permission':'instagram_manage_insights','status':'declined'},
           {'permission':'pages_show_list','status':'granted'},
           {'permission':'pages_read_engagement','status':'granted'},
           {'permission':'email','status':'granted'}]})])
        flags=inspect_graph_permissions('fixture',http=http)
        self.assertTrue(flags['instagram_basic'])
        self.assertFalse(flags['instagram_manage_insights'])
        self.assertTrue(flags['pages_show_list'])
        self.assertTrue(flags['pages_read_engagement'])
        self.assertNotIn('email',flags)
        self.assertNotIn('fixture',str(flags))

if __name__=='__main__':unittest.main()
