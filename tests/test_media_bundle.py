"""Real Reel and 20-page carousel ingestion contract; deterministic, no network."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from reelbrain.contracts import Observation
from reelbrain.store import KnowledgeStore


class PublicBundleTests(unittest.TestCase):
    def test_all_carousel_pages_are_collected_in_order(self):
        from reelbrain.public_bundle import acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def fake_gallery(argv, **kw):
                self.assertIn('--config-ignore', argv)
                self.assertIn('--no-input', argv)
                self.assertIn('--range', argv)
                self.assertTrue(argv[-1].startswith('https://www.instagram.com/p/'))
                base = Path(argv[argv.index('-D') + 1])
                (base / 'slide_1.jpg').write_bytes(b'\xff\xd8\xff' + b'A' * 100)
                (base / 'slide_2.png').write_bytes(b'\x89PNG\r\n\x1a\n' + b'B' * 100)
                (base / 'slide_10.webp').write_bytes(b'RIFF' + b'\x00'*4 + b'WEBP' + b'C'*100)
                for index,name in enumerate(('slide_1.jpg','slide_2.png','slide_10.webp'),1):
                    (base/(name+'.json')).write_text(json.dumps({'post_shortcode':'EXAMPLE1','count':3,'num':index,'typename':'GraphSidecar'}))
                return subprocess.CompletedProcess(argv, 0, '', '')
            bundle = acquire_public_bundle('https://www.instagram.com/p/EXAMPLE1/?utm_source=x',
                                           Path(td), gallery_runner=fake_gallery)
            self.assertEqual([p.name for p in bundle.paths], ['slide_1.jpg', 'slide_2.png', 'slide_10.webp'])
            self.assertEqual(bundle.provider, 'gallery-dl-public')

    def test_carousel_cover_only_or_unverified_manifest_is_rejected(self):
        from reelbrain.public_bundle import acquire_public_bundle,PublicBundleError
        for count,num,typename in ((5,1,'GraphSidecar'),(1,1,'GraphSidecar'),(None,1,'GraphImage')):
            with self.subTest(count=count,typename=typename),tempfile.TemporaryDirectory() as td:
                def gallery(argv,**kwargs):
                    base=Path(argv[argv.index('-D')+1])
                    (base/'cover.jpg').write_bytes(b'\xff\xd8\xff'+b'X'*100)
                    (base/'cover.jpg.json').write_text(json.dumps({'post_shortcode':'EXAMPLE1','count':count,'num':num,'typename':typename}))
                    return subprocess.CompletedProcess(argv,0,'','')
                with self.assertRaises(PublicBundleError):
                    acquire_public_bundle('https://instagram.com/p/EXAMPLE1/',Path(td),gallery_runner=gallery)

    def test_single_image_post_with_verified_manifest_is_allowed(self):
        from reelbrain.public_bundle import acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def gallery(argv,**kwargs):
                self.assertIn('--write-metadata',argv)
                base=Path(argv[argv.index('-D')+1])
                (base/'image.jpg').write_bytes(b'\xff\xd8\xff'+b'X'*100)
                (base/'image.jpg.json').write_text(json.dumps({'post_shortcode':'EXAMPLE1','count':1,'num':1,'typename':'GraphImage'}))
                return subprocess.CompletedProcess(argv,0,'','')
            bundle=acquire_public_bundle('https://instagram.com/p/EXAMPLE1/',Path(td),gallery_runner=gallery)
            self.assertEqual(len(bundle.paths),1)
            self.assertFalse(list(Path(td).rglob('*.json')))

    def test_reel_falls_back_after_yt_dlp_failed(self):
        from reelbrain.public_bundle import acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def fail_yt(argv, **kw):
                return subprocess.CompletedProcess(argv, 1, '', 'ERROR: login required')
            def gallery(argv, **kw):
                base = Path(argv[argv.index('-D')+1])
                (base/'reel.mp4').write_bytes(b'\x00\x00\x00\x18ftypisom' + b'0'*100)
                return subprocess.CompletedProcess(argv, 0, '', '')
            bundle = acquire_public_bundle('https://instagram.com/reel/EXAMPLE1/', Path(td),
                                           yt_runner=fail_yt, gallery_runner=gallery)
            self.assertEqual(bundle.provider, 'gallery-dl-public')
            self.assertEqual(bundle.paths[0].suffix, '.mp4')

    def test_fake_media_is_rejected_even_if_downloader_reports_success(self):
        from reelbrain.public_bundle import PublicBundleError, acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def fake(argv, **kw):
                base = Path(argv[argv.index('-D')+1])
                (base/'page_1.jpg').write_bytes(b'<html>login required</html>')
                return subprocess.CompletedProcess(argv, 0, '', '')
            with self.assertRaises(PublicBundleError):
                acquire_public_bundle('https://instagram.com/p/EXAMPLE1/', Path(td),gallery_runner=fake)

    def test_error_message_contains_no_raw_urls_or_provider_tokens(self):
        from reelbrain.public_bundle import PublicBundleError, acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def fail(argv, **kw):
                return subprocess.CompletedProcess(argv, 1, '', '403 TOKEN_SHOULD_NOT_LEAK')
            with self.assertRaises(PublicBundleError) as cm:
                acquire_public_bundle('https://instagram.com/p/EXAMPLE1/', Path(td),gallery_runner=fail)
            self.assertNotIn('TOKEN_SHOULD_NOT_LEAK', str(cm.exception))

    def test_missing_slides_fail_instead_of_fabricating_full_coverage(self):
        from reelbrain.public_bundle import PublicBundleError, acquire_public_bundle
        with tempfile.TemporaryDirectory() as td:
            def excess(argv, **kw):
                base=Path(argv[argv.index('-D')+1])
                for i in range(1,22):
                    (base/f'page_{i:02}.jpg').write_bytes(b'\xff\xd8\xff' + b'X'*200)
                return subprocess.CompletedProcess(argv, 0, '', '')
            with self.assertRaises(PublicBundleError):
                acquire_public_bundle('https://instagram.com/p/EXAMPLE1/',Path(td),gallery_runner=excess)


class CarouselEngineTests(unittest.TestCase):
    def test_two_slides_both_read_with_page_citations_and_one_receipt(self):
        from reelbrain.engine import LocalPipelineEngine
        with tempfile.TemporaryDirectory() as td:
            a=Path(td)/'slide1.jpg';b=Path(td)/'slide2.png'
            a.write_bytes(b'synthetic 1');b.write_bytes(b'synthetic 2')
            store=KnowledgeStore(Path(td)/'evidence.sqlite')
            try:
                def fake_ocr(path):
                    return [Observation('Visit https://github.com/example/'+path.stem,kind='ocr',locator='image:1')]
                output=LocalPipelineEngine(store,ocr=fake_ocr).ingest(
                    [a,b], 'https://www.instagram.com/p/EXAMPLE1/')
                self.assertTrue(output.get('processing_receipt_id'))
                self.assertEqual(output['stage_observations']['ocr'],2)
                rows=store.con.execute("SELECT locator FROM evidence").fetchall()
                self.assertEqual({r[0] for r in rows},{'slide:01/image:1','slide:02/image:1'})
                self.assertEqual(output['resource_count'],2)
            finally:store.close()

    def test_ten_page_post_preserves_last_page_links_and_coverage(self):
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.media_evidence_summary import build_media_summary
        class Vision:
            def analyze(self,path):
                return [Observation('Technical workflow '+path.stem,kind='model_inference',locator='image:1')]
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            files=[root/f'page_{n:02d}.jpg' for n in range(1,11)]
            for p in files:p.write_bytes(b'fixture')
            store=KnowledgeStore(root/'evidence.sqlite')
            try:
                result=LocalPipelineEngine(store,ocr=lambda p:[Observation('https://github.com/example/'+p.stem,kind='ocr',locator='image:1')],video_model=Vision()).ingest(files,'https://instagram.com/p/EXAMPLE1/',allow_external=True)
                self.assertEqual(result['asset_count'],10)
                self.assertEqual(result['stage_observations']['vlm'],10)
                self.assertEqual(result['resource_count'],10)
                rows=[dict(r) for r in store.con.execute('select kind,locator,verbatim from evidence').fetchall()]
                self.assertTrue(any(r['locator'].startswith('slide:10/') and 'page_10' in r['verbatim'] for r in rows))
                summary=build_media_summary(rows,{**result,'media_processed':True})
                self.assertEqual(summary['processing_stage'],'completed')
                self.assertEqual(summary['content']['asset_count'],10)
                self.assertEqual(summary['content']['completed_asset_count'],10)
            finally:store.close()

    def test_post_never_reuses_a_single_hosted_video_transcript(self):
        from reelbrain.durable_worker import reusable_hosted_audio
        class PG:
            def cursor(self):raise AssertionError('Post must use its own per-slide audio')
        self.assertIsNone(reusable_hosted_audio(PG(),'https://instagram.com/p/EXAMPLE1/'))

    def test_asset_count_over_twenty_fails_before_extraction(self):
        from reelbrain.engine import LocalPipelineEngine
        with tempfile.TemporaryDirectory() as td:
            store=KnowledgeStore(Path(td)/'evidence.sqlite')
            p=Path(td)/'slide.jpg';p.write_bytes(b'fixture')
            try:
                with self.assertRaises(ValueError):
                    LocalPipelineEngine(store,ocr=lambda x:[]).ingest(
                        [p]*21,'https://www.instagram.com/p/EXAMPLE1/')
            finally:store.close()

if __name__ == '__main__':
    unittest.main()
