"""Offline contract tests for the post-only budgeted fallback."""
import unittest
from unittest.mock import patch
from reelbrain.public_media import PublicMediaError
from reelbrain.meta_business_media import MetaSourceAsset
from reelbrain.apify_post_media import parse_post_assets, acquire_apify_post, budget_available

URL='https://www.instagram.com/p/Example123/'
A='https://scontent.cdninstagram.com/a.jpg'
B='https://scontent.cdninstagram.com/b.jpg'
def image(url):return {'type':'Image','displayUrl':url}
def post(**kwargs):return {'shortCode':'Example123','url':URL,'type':'Sidecar','childPosts':[image(A),image(B)],'images':[A,B],**kwargs}
def limits(used=0,maximum=5,active=0):
    return {'data':{'current':{'monthlyUsageUsd':used,'activeActorJobCount':active},'limits':{'maxMonthlyUsageUsd':maximum}}}
class Reply:
    def __init__(self,data,status=200):self.data,self.status_code=data,status
    def json(self):return self.data
class Client:
    def __init__(self,lim=None,items=None,status=200):
        self.lim=lim if lim is not None else limits()
        self.items=items if items is not None else [post()]
        self.status=status;self.posts=[]
    def get(self,*args,**kwargs):return Reply(self.lim)
    def post(self,*args,**kwargs):self.posts.append((args,kwargs));return Reply(self.items,self.status)

class ApifyPostTests(unittest.TestCase):
    def test_order_and_single_image(self):
        self.assertEqual(parse_post_assets(URL,[post()]),(MetaSourceAsset('IMAGE',A),MetaSourceAsset('IMAGE',B)))
        self.assertEqual(parse_post_assets(URL,[{'shortCode':'Example123','type':'Image','displayUrl':A}]),(MetaSourceAsset('IMAGE',A),))
    def test_incomplete_wrong_private_or_duplicate(self):
        for row in [dict(post(),shortCode='OTHER'),dict(post(),isPrivate=True),dict(post(),childPosts=[image(A)]),dict(post(),childPosts=[image(A),image(A)],images=[]),dict(post(),childPosts=[image(A),image('https://example.org/x.jpg')])]:
            with self.subTest(row=row),self.assertRaises(PublicMediaError):parse_post_assets(URL,[row])
    def test_budget_fails_closed(self):
        for data in [limits(4.49),limits(maximum=100),limits(active=1),{},limits(-1)]:
            with self.subTest(data=data):self.assertFalse(budget_available(data))
        self.assertTrue(budget_available(limits(1)))
    def test_no_network_run_if_budget_unavailable(self):
        c=Client(lim=limits(4.49))
        with self.assertRaises(PublicMediaError):acquire_apify_post(URL,'unused','fixture',http=c)
        self.assertEqual(c.posts,[])
    def test_bounded_single_source_request(self):
        c=Client()
        with patch('reelbrain.apify_post_media.download_source_assets',return_value='bundle') as d:
            self.assertEqual(acquire_apify_post(URL,'unused','fixture',http=c),'bundle')
        self.assertEqual(len(c.posts),1)
        params=c.posts[0][1]['params']
        self.assertEqual(params['maxItems'],1);self.assertEqual(params['maxTotalChargeUsd'],0.02)
        self.assertEqual(c.posts[0][1]['json']['directUrls'],[URL])
        self.assertEqual(len(d.call_args.args[0]),2)
    def test_free_path_never_calls_apify_and_reels_unchanged(self):
        from reelbrain.scrapecreators_media import acquire_with_public_provider
        with patch.dict('os.environ',{'REELBRAIN_POST_APIFY_API_TOKEN':'fixture'},clear=True),patch('reelbrain.meta_business_media.acquire_with_meta_fallback',return_value='free'),patch('reelbrain.apify_post_media.acquire_apify_post') as a:
            self.assertEqual(acquire_with_public_provider(URL,'unused',None),'free');a.assert_not_called()
        with patch.dict('os.environ',{'REELBRAIN_POST_APIFY_API_TOKEN':'fixture'},clear=True),patch('reelbrain.meta_business_media.acquire_with_meta_fallback',side_effect=PublicMediaError('original failure')),patch('reelbrain.apify_post_media.acquire_apify_post') as a:
            with self.assertRaises(PublicMediaError):acquire_with_public_provider('https://www.instagram.com/reel/Example123/','unused',None)
            a.assert_not_called()
    def test_post_falls_back_and_preserves_optional_backup(self):
        from reelbrain.scrapecreators_media import acquire_with_public_provider
        env={'REELBRAIN_POST_APIFY_API_TOKEN':'fixture','REELBRAIN_MEDIA_SCRAPECREATORS_ENABLED':'1','REELBRAIN_MEDIA_SCRAPECREATORS_API_KEY':'backup'}
        with patch.dict('os.environ',env,clear=True),patch('reelbrain.meta_business_media.acquire_with_meta_fallback',side_effect=PublicMediaError('free failed')),patch('reelbrain.apify_post_media.acquire_apify_post',side_effect=PublicMediaError('public media unavailable: credits_exhausted')),patch('reelbrain.scrapecreators_media.acquire_scrapecreators_bundle',return_value='backup') as b:
            self.assertEqual(acquire_with_public_provider(URL,'unused',None),'backup')
            b.assert_called_once_with(URL,'unused','backup')
