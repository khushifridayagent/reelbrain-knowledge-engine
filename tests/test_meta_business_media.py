"""Read-only official Meta Business Discovery may supply REAL public professional media.

No Internet, tokens, profile cookies, or media bytes are used by this test.
"""
import tempfile, unittest
from pathlib import Path
from unittest.mock import patch

SRC='https://www.instagram.com/reel/DgGHCjZIZtW/'


def response_for(username='aimortal.ig',code='DgGHCjZIZtW',media_url='https://scontent-abc.cdninstagram.com/v/t50.2886-16/video.mp4?ig_cache_key=sample'):
    return {'business_discovery':{'username':username,'media':{'data':[
        {'id':'179121111','permalink':f'https://www.instagram.com/p/{code}/',
         'media_type':'VIDEO','media_url':media_url}]}}}


class Response:
    status_code=200
    def __init__(self,json):self.payload=json
    def json(self):return self.payload
    def raise_for_status(self):pass


class FakeClient:
    def __init__(self,payload):self.payload=payload;self.requests=[]
    def get(self,url,**kwargs):
        self.requests.append((url,kwargs))
        return Response(self.payload)


class MetaDiscoveryTests(unittest.TestCase):
    def test_find_exact_reel_from_creator_official_business_discovery(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery
        http=FakeClient(response_for())
        target=MetaBusinessDiscovery('fixture','17841400001234567',http=http)
        found=target.find(SRC,'aimortal.ig')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0].media_type,'VIDEO')
        self.assertTrue(found[0].media_url.startswith('https://scontent-abc.cdninstagram.com/'))
        self.assertIn('business_discovery.username(aimortal.ig)',http.requests[0][1]['params']['fields'])
        self.assertEqual(http.requests[0][1]['headers']['Authorization'],'Bearer fixture')
        self.assertNotIn('access_token',str(http.requests[0][1]['params']))

    def test_alias_p_and_reel_match_by_exact_shortcode_only(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery, MetaMediaUnavailable
        client=MetaBusinessDiscovery('fixture','17841400001234567',http=FakeClient(response_for(code='OTHER_REEL')))
        with self.assertRaises(MetaMediaUnavailable):client.find(SRC,'aimortal.ig')

    def test_wrong_account_cannot_be_used_as_video_evidence(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery, MetaMediaUnavailable
        client=MetaBusinessDiscovery('fixture','17841400001234567',http=FakeClient(response_for(username='impersonator')))
        with self.assertRaises(MetaMediaUnavailable):client.find(SRC,'aimortal.ig')

    def test_if_meta_omits_video_url_due_licensed_audio_defer_not_succeed(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery, MetaMediaUnavailable
        client=MetaBusinessDiscovery('fixture','17841400001234567',http=FakeClient(response_for(media_url=None)))
        with self.assertRaises(MetaMediaUnavailable):client.find(SRC,'aimortal.ig')

    def test_carousel_all_20_children_required_and_order_preserved(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        imgs=[{'id':str(k),'media_type':'IMAGE',
               'media_url':f'https://scontent.cdninstagram.com/a/{k}.jpg'} for k in range(1,21)]
        payload={'business_discovery':{'username':'somecreator','media':{'data':[{
            'permalink':'https://www.instagram.com/p/DgGHCjZIZtW/',
            'media_type':'CAROUSEL_ALBUM','children':{'data':imgs}}]}}}
        client=MetaBusinessDiscovery('fixture','17841400001234567',http=FakeClient(payload))
        found=client.find('https://www.instagram.com/p/DgGHCjZIZtW/','somecreator')
        self.assertEqual(len(found),20)
        self.assertTrue(found[0].media_url.endswith('/1.jpg'))
        self.assertTrue(found[-1].media_url.endswith('/20.jpg'))
        del imgs[4]['media_url']
        with self.assertRaises(MetaMediaUnavailable):client.find('https://www.instagram.com/p/DgGHCjZIZtW/','somecreator')

    def test_reject_non_https_or_untrusted_cdn(self):
        from reelbrain.meta_business_media import valid_meta_media_url
        for url in ('http://scontent.cdninstagram.com/a.mp4',
                    'https://localhost/a.mp4',
                    'https://cdninstagram.com.evil.example/a.mp4',
                    'https://username:password@scontent.cdninstagram.com/a.mp4',
                    'https://scontent.cdninstagram.com:444/a.mp4'):
            self.assertFalse(valid_meta_media_url(url),url)
        self.assertTrue(valid_meta_media_url('https://scontent.cdninstagram.com/a.mp4?oh=x'))

    def test_bad_creator_username_not_sent_to_graph(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        http=FakeClient(response_for())
        with self.assertRaises(MetaMediaUnavailable):
            MetaBusinessDiscovery('fixture','17841400001234567',http=http).find(SRC,'evil){/media{token}}')
        self.assertEqual(http.requests,[])

    def test_absent_meta_token_keeps_existing_public_downloader(self):
        from reelbrain.meta_business_media import meta_fallback_enabled
        with patch.dict('os.environ',{},clear=True):
            self.assertFalse(meta_fallback_enabled())
        with patch.dict('os.environ',{'REELBRAIN_META_GRAPH_TOKEN':'fixture',
            'REELBRAIN_META_IG_USER_ID':'17841400001234567','REELBRAIN_META_BUSINESS_DISCOVERY_ENABLED':'1'},clear=True):
            self.assertTrue(meta_fallback_enabled())

    def test_existing_public_downloader_always_gets_first_chance(self):
        from reelbrain.meta_business_media import acquire_with_meta_fallback
        class PG:
            def cursor(self):raise AssertionError('Should not query creators when download works')
        bundle=object()
        found=acquire_with_meta_fallback(SRC,Path('/tmp'),PG(),
            public_fetch=lambda *args,**kwargs:bundle,meta_fetch=lambda *args,**kwargs:None)
        self.assertIs(found,bundle)

    def test_on_403_and_authorized_pro_account_fallback_uses_creator_from_db(self):
        from reelbrain.meta_business_media import acquire_with_meta_fallback
        from reelbrain.public_media import PublicMediaError
        class PGCursor:
            def __init__(self):self.params=None
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def execute(self,sql,args):self.params=args
            def fetchone(self):return ('aimortal.ig',)
        class PG:
            def cursor(self):return PGCursor()
        seen={}
        def fail_public(*a,**kw):raise PublicMediaError('Public Reel download unavailable: http_forbidden')
        def lookup(*args,**kwargs):seen['args']=args;return 'actual_meta_media'
        env={'REELBRAIN_META_GRAPH_TOKEN':'fixture','REELBRAIN_META_IG_USER_ID':'17841400001234567',
             'REELBRAIN_META_BUSINESS_DISCOVERY_ENABLED':'1'}
        with patch.dict('os.environ',env,clear=True):
            result=acquire_with_meta_fallback(SRC,Path('/tmp'),PG(),
                public_fetch=fail_public,meta_fetch=lookup)
        self.assertEqual(result,'actual_meta_media')
        self.assertEqual(seen['args'][1],'aimortal.ig')

    def test_missing_token_prevents_meta_network_and_preserves_access_failure(self):
        from reelbrain.meta_business_media import acquire_with_meta_fallback
        from reelbrain.public_media import PublicMediaError
        class PG:
            def cursor(self):raise AssertionError('Should not query unless fallback configured')
        def fail_public(*a,**kw):raise PublicMediaError('Public Reel download unavailable: http_forbidden')
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(PublicMediaError):
                acquire_with_meta_fallback(SRC,Path('/tmp'),PG(),
                    public_fetch=fail_public,
                    meta_fetch=lambda *args: (_ for _ in ()).throw(AssertionError('must not call Meta')))

    def test_complete_2_page_carousel_temp_download_preserves_order(self):
        from reelbrain.meta_business_media import acquire_meta_bundle
        files=[{'id':'A','media_type':'IMAGE',
                 'media_url':'https://scontent.cdninstagram.com/a.jpg'},
               {'id':'B','media_type':'IMAGE',
                 'media_url':'https://scontent.cdninstagram.com/b.jpg'}]
        payload={'business_discovery':{'username':'somecreator','media':{'data':[{
            'permalink':'https://www.instagram.com/p/DgGHCjZIZtW/',
            'media_type':'CAROUSEL_ALBUM','children':{'data':files}}]}}}
        class SourceStream:
            status_code=200
            headers={'content-length':'60'}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def iter_bytes(self,chunk_size=1024):yield bytes.fromhex('ffd8ff')+b'X'*58
        class Downloader:
            def __init__(self):self.paths=[]
            def stream(self,method,url,**kwargs):self.paths.append(url);return SourceStream()
        dl=Downloader()
        with tempfile.TemporaryDirectory() as d:
            bundle=acquire_meta_bundle('https://www.instagram.com/p/DgGHCjZIZtW/',
                 'somecreator','fixture','17841400001234567',d,
                 lookup_http=FakeClient(payload),download_http=dl)
            self.assertEqual(len(bundle.paths),2)
            self.assertEqual([p.name for p in bundle.paths],['page_01.jpg','page_02.jpg'])
            self.assertTrue(all(p.is_file() for p in bundle.paths))
            self.assertEqual(bundle.provider,'meta-business-discovery-official')


    def test_production_media_lookup_repairs_page_id_with_one_linked_ig(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery
        class Result:
            status_code=200
            def __init__(self,payload):self.payload=payload
            def json(self):return self.payload
            def raise_for_status(self):pass
        class Requests:
            def __init__(self):self.calls=[]
            def get(self,url,**kwargs):
                self.calls.append((url,kwargs))
                count=len(self.calls)
                if count==1:
                    return Result({'error':{'code':100,'message':'raw message untrusted'}})
                if count==2:
                    return Result({'data':[{'id':'11223344',
                        'instagram_business_account':{'id':'17841400001234567'}}]})
                return Result(response_for())
        http=Requests()
        found=MetaBusinessDiscovery('fixture','1234567890',http=http).find(SRC,'aimortal.ig')
        self.assertEqual(len(found),1)
        self.assertEqual(len(http.calls),3)
        self.assertTrue(http.calls[-1][0].endswith('/17841400001234567'))

    def test_ambiguous_page_connections_fail_closed_without_media_lookup(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        class Result:
            status_code=200
            def __init__(self,payload):self.payload=payload
            def json(self):return self.payload
            def raise_for_status(self):pass
        class Requests:
            def __init__(self):self.calls=[]
            def get(self,url,**kwargs):
                self.calls.append((url,kwargs))
                if len(self.calls)==1:
                    return Result({'error':{'code':100}})
                return Result({'data':[
                  {'instagram_business_account':{'id':'17841400001234567'}},
                  {'instagram_business_account':{'id':'17841400007654321'}}]})
        http=Requests()
        with self.assertRaises(MetaMediaUnavailable):
            MetaBusinessDiscovery('fixture','1234567890',http=http).find(SRC,'aimortal.ig')
        self.assertEqual(len(http.calls),2)

    def test_graph_rate_limit_is_not_reported_as_permission_failure(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        from reelbrain.access_backoff import access_backoff_seconds
        http=FakeClient({'error':{'code':4,'message':'private message'}})
        with self.assertRaises(MetaMediaUnavailable) as err:
            MetaBusinessDiscovery('fixture','17841400001234567',http=http).find(SRC,'aimortal.ig')
        self.assertIn('app_rate_limited',str(err.exception))
        self.assertEqual(access_backoff_seconds(err.exception),43200)
        self.assertNotIn('private message',str(err.exception))
        self.assertEqual(len(http.requests),1)

    def test_expired_token_is_distinct_from_missing_media(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        http=FakeClient({'error':{'code':190,'message':'private token'}})
        with self.assertRaisesRegex(MetaMediaUnavailable,'token_expired_or_invalid'):
            MetaBusinessDiscovery('fixture','17841400001234567',http=http).find(SRC,'aimortal.ig')
        self.assertEqual(len(http.requests),1)

    def test_graph_missing_url_and_unsupported_cdn_are_distinct(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        for value,reason in [(None,'original_media_url_omitted'),
                             ('https://example.org/video.mp4','untrusted_media_url')]:
            with self.subTest(value=value):
                with self.assertRaisesRegex(MetaMediaUnavailable,reason):
                    MetaBusinessDiscovery('fixture','17841400001234567',
                         http=FakeClient(response_for(media_url=value))).find(SRC,'aimortal.ig')

    def test_reel_cannot_be_marked_acquired_from_static_image(self):
        from reelbrain.meta_business_media import MetaBusinessDiscovery,MetaMediaUnavailable
        payload=response_for()
        payload['business_discovery']['media']['data'][0]['media_type']='IMAGE'
        with self.assertRaisesRegex(MetaMediaUnavailable,'reel_original_video_missing'):
            MetaBusinessDiscovery('fixture','17841400001234567',
                  http=FakeClient(payload)).find(SRC,'aimortal.ig')

if __name__=='__main__':unittest.main()
