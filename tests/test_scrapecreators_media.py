"""Media acquisition contract; no live provider calls or credentials in CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from reelbrain.public_media import PublicMediaError
from reelbrain.meta_business_media import MetaMediaUnavailable,MetaSourceAsset
from reelbrain.scrapecreators_media import (
    parse_public_assets, acquire_scrapecreators_bundle, media_provider_enabled)

URL='https://www.instagram.com/reel/DgGHCjZIZtW/'
CDN='https://scontent.cdninstagram.com/video.mp4'
def payload(node):
    return {'success':True,'credits_charged':1,'credits_remaining':99,
            'data':{'xdt_shortcode_media':node}}
def video(**kw):
    return {'shortcode':'DgGHCjZIZtW','is_video':True,'video_url':CDN,**kw}

class MediaProviderTests(unittest.TestCase):
    def test_exact_reel_and_no_thumbnail_substitution(self):
        self.assertEqual(parse_public_assets(URL,payload(video())),
                         (MetaSourceAsset('VIDEO',CDN),))
        for bad in (video(shortcode='OTHER'),video(video_url=None),
                    video(video_url='https://example.org/a.mp4'),video(is_video=False)):
            with self.subTest(bad=bad):
                with self.assertRaises(PublicMediaError):
                    parse_public_assets(URL,payload(bad))

    def test_carousel_order_and_missing_page(self):
        post='https://www.instagram.com/p/DgGHCjZIZtW/'
        slides=[{'is_video':False,'display_url':f'https://scontent.cdninstagram.com/{i}.jpg'}
                for i in range(20)]
        node={'shortcode':'DgGHCjZIZtW','__typename':'XDTGraphSidecar',
              'edge_sidecar_to_children':{'count':20,'edges':[{'node':x} for x in slides]}}
        self.assertEqual(len(parse_public_assets(post,payload(node))),20)
        self.assertTrue(parse_public_assets(post,payload(node))[-1].media_url.endswith('/19.jpg'))
        node['edge_sidecar_to_children']['edges'].pop()
        with self.assertRaises(PublicMediaError):parse_public_assets(post,payload(node))

    def test_opt_in_and_separate_token_required(self):
        with patch.dict('os.environ',{},clear=True):
            self.assertFalse(media_provider_enabled())
        with patch.dict('os.environ',{'REELBRAIN_MEDIA_SCRAPECREATORS_ENABLED':'1',
             'REELBRAIN_MEDIA_SCRAPECREATORS_API_KEY':'fixture'},clear=True):
            self.assertTrue(media_provider_enabled())

    def test_request_only_direct_url_no_permanent_download(self):
        class Reply:
            status_code=200
            def json(self):return payload(video())
        class Client:
            def get(self,url,**kwargs):
                self.kwargs=kwargs;return Reply()
        c=Client()
        with tempfile.TemporaryDirectory() as td:
            with patch('reelbrain.scrapecreators_media.download_source_assets',return_value='bundle') as download:
                self.assertEqual(acquire_scrapecreators_bundle(URL,td,'fixture',http=c),'bundle')
                self.assertEqual(c.kwargs['params']['download_media'],'false')
                self.assertEqual(c.kwargs['params']['url'],URL)
                self.assertEqual(c.kwargs['headers']['x-api-key'],'fixture')
                self.assertEqual(download.call_args.args[0],(MetaSourceAsset('VIDEO',CDN),))

    def test_exhausted_provider_does_not_attempt_download(self):
        class Reply:
            status_code=402
            def json(self):return {}
        class Client:
            def get(self,*a,**k):return Reply()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(PublicMediaError,'credits_exhausted'):
                acquire_scrapecreators_bundle(URL,td,'fixture',http=Client())

    def test_private_owner_and_missing_carousel_coverage_are_rejected(self):
        with self.assertRaises(PublicMediaError):
            parse_public_assets(URL,payload(video(owner={'is_private':True})))
        post='https://www.instagram.com/p/DgGHCjZIZtW/'
        node={'shortcode':'DgGHCjZIZtW','__typename':'XDTGraphSidecar',
              'edge_sidecar_to_children':{'edges':[]}}
        with self.assertRaises(PublicMediaError):parse_public_assets(post,payload(node))

    def test_disabled_fallback_preserves_prior_error(self):
        from reelbrain.scrapecreators_media import acquire_with_public_provider
        with patch.dict('os.environ',{},clear=True):
            with patch('reelbrain.meta_business_media.acquire_with_meta_fallback',
                       side_effect=PublicMediaError('original failure')):
                with self.assertRaisesRegex(PublicMediaError,'original failure'):
                    acquire_with_public_provider(URL,'unused',None)

    def test_enabled_fallback_uses_same_source(self):
        from reelbrain.scrapecreators_media import acquire_with_public_provider
        with patch.dict('os.environ',{'REELBRAIN_MEDIA_SCRAPECREATORS_ENABLED':'1',
                 'REELBRAIN_MEDIA_SCRAPECREATORS_API_KEY':'fixture'},clear=True):
            with patch('reelbrain.meta_business_media.acquire_with_meta_fallback',
                       side_effect=PublicMediaError('original failure')):
                with patch('reelbrain.scrapecreators_media.acquire_scrapecreators_bundle',
                           return_value='bundle') as fetch:
                    self.assertEqual(acquire_with_public_provider(URL,'unused',None),'bundle')
                    fetch.assert_called_once_with(URL,'unused','fixture')
