import subprocess
import tempfile
import unittest
from pathlib import Path
from reelbrain.public_media import PublicMediaError, acquire_public_reel, canonical_reel

class PublicMediaTests(unittest.TestCase):
    def test_canonical_only_ig_reel_and_filters_query(self):
        self.assertEqual(canonical_reel('https://www.instagram.com/reel/DaQLc80PIBU/?igsh=foo'), 'https://www.instagram.com/reel/DaQLc80PIBU/')
        for bad in ('http://www.instagram.com/reel/DaQLc80PIBU/', 'https://instagram.com@evil.com/reel/X1111/',
                    'https://www.instagram.com/p/DaQLc80PIBU/', 'https://evil.com/reel/DaQLc80PIBU/',
                    'https://www.instagram.com/reel/X/','https://www.instagram.com/reel/DaQLc80PIBU/another',
                    'https://www.instagram.com:8080/reel/DaQLc80PIBU/'):
            with self.subTest(bad=bad):
                with self.assertRaises(PublicMediaError): canonical_reel(bad)

    def test_accepts_bounded_real_mp4_and_passes_no_cookies(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake_run(cmd, **kw):
                calls.append((cmd,kw))
                dest=Path(tmp)/'DaQLc80PIBU.mp4'
                dest.write_bytes(b'\x00\x00\x00\x1cftypisom'+b'\x00'*100)
                return subprocess.CompletedProcess(cmd,0,stdout='',stderr='')
            result=acquire_public_reel('https://www.instagram.com/reel/DaQLc80PIBU/?igsh=X',Path(tmp),runner=fake_run)
            self.assertTrue(result.is_file())
            self.assertEqual(len(calls),1)
            self.assertIn('--no-playlist',calls[0][0])
            self.assertIn('--ignore-config',calls[0][0])
            self.assertIn('--no-cookies-from-browser',calls[0][0])
            self.assertEqual(calls[0][0][-1],'https://www.instagram.com/reel/DaQLc80PIBU/')
            self.assertFalse(calls[0][1]['shell'] if 'shell' in calls[0][1] else False)

    def test_no_file_or_bad_header_fails_without_fake_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd,**kw):return subprocess.CompletedProcess(cmd,0,'','')
            with self.assertRaises(PublicMediaError):
                acquire_public_reel('https://www.instagram.com/reel/DaQLc80PIBU/',Path(tmp),runner=fake_run)
            Path(tmp,'DaQLc80PIBU.mp4').write_bytes(b'<html>some login page')
            with self.assertRaises(PublicMediaError):
                acquire_public_reel('https://www.instagram.com/reel/DaQLc80PIBU/',Path(tmp),runner=fake_run)

    def test_yt_dlp_exit_error_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(cmd,**kw):return subprocess.CompletedProcess(cmd,1,'','403 login required ' * 1000)
            with self.assertRaises(PublicMediaError) as cm:
                acquire_public_reel('https://www.instagram.com/reel/DaQLc80PIBU/',Path(tmp),runner=fake_run)
            self.assertLess(len(str(cm.exception)),300)


    def test_reel_downloader_reports_safe_failure_category_without_exposing_original_error(self):
        cases=[
            ("ERROR: [Instagram] LOGIN REQUIRED; please provide cookies", "login_required"),
            ("ERROR: HTTP Error 403: Forbidden", "http_forbidden"),
            ("ERROR: HTTP Error 429: Too Many Requests", "rate_limited"),
            ("ERROR: Unable to extract video data", "extractor_unavailable"),
        ]
        for raw, category in cases:
            with self.subTest(category=category):
                with tempfile.TemporaryDirectory() as tmp:
                    def fake(cmd, **kwargs):
                        return subprocess.CompletedProcess(cmd,1,'',raw + ' PRIVATE_TOKEN_SHOULD_NOT_LEAK')
                    with self.assertRaises(PublicMediaError) as failed:
                        acquire_public_reel('https://www.instagram.com/reel/DaQLc80PIBU/',Path(tmp),runner=fake)
                    self.assertIn(category,str(failed.exception))
                    self.assertNotIn('PRIVATE_TOKEN_SHOULD_NOT_LEAK',str(failed.exception))

if __name__=='__main__':unittest.main()