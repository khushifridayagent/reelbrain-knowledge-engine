"""Real Reel and 20-page carousel ingestion contract; deterministic, no network."""
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
                return subprocess.CompletedProcess(argv, 0, '', '')
            bundle = acquire_public_bundle('https://www.instagram.com/p/EXAMPLE1/?utm_source=x',
                                           Path(td), gallery_runner=fake_gallery)
            self.assertEqual([p.name for p in bundle.paths], ['slide_1.jpg', 'slide_2.png', 'slide_10.webp'])
            self.assertEqual(bundle.provider, 'gallery-dl-public')

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
