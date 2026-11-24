"""Optional authorized Instagram session improves retrieval without exposing cookies."""
import base64
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reelbrain.public_media import acquire_public_reel
from reelbrain.public_bundle import acquire_public_bundle


class SessionTests(unittest.TestCase):
    def test_yt_dlp_receives_optional_session_file_without_default(self):
        with tempfile.TemporaryDirectory() as root:
            cookie=Path(root)/'cookies.txt'
            cookie.write_text('# Netscape HTTP Cookie File\n', encoding='utf8')
            os.chmod(cookie,0o600)
            cmds=[]
            def runner(cmd,**kw):
                cmds.append(cmd)
                p=Path(root)/'output'/'EXAMPLE123.mp4'
                p.parent.mkdir(exist_ok=True)
                p.write_bytes(b'\x00\x00\x00\x18ftypisom'+b'x'*80)
                return subprocess.CompletedProcess(cmd,0,'','')
            folder=Path(root)/'output';folder.mkdir(exist_ok=True)
            acquire_public_reel('https://instagram.com/reel/EXAMPLE123/',folder,
                                runner=runner,cookies_file=cookie)
            self.assertEqual(cmds[0][cmds[0].index('--cookies')+1],str(cookie))
            self.assertNotIn('--cookies-from-browser',cmds[0])
    def test_gallery_receives_optional_cookie_file(self):
        with tempfile.TemporaryDirectory() as root:
            cookie=Path(root)/'cookies.txt'
            cookie.write_text('# Netscape HTTP Cookie File\n',encoding='utf8')
            os.chmod(cookie,0o600)
            def gallery(cmd,**kw):
                self.assertEqual(cmd[cmd.index('--cookies')+1],str(cookie))
                folder=Path(cmd[cmd.index('-D')+1])
                (folder/'slide_1.jpg').write_bytes(bytes.fromhex('ffd8ff')+b'x'*50)
                return subprocess.CompletedProcess(cmd,0,'','')
            bundle=acquire_public_bundle('https://instagram.com/p/EXAMPLE123/',Path(root),
                                         gallery_runner=gallery,cookies_file=cookie)
            self.assertEqual(len(bundle.paths),1)
    def test_missing_or_world_readable_cookie_file_is_rejected(self):
        from reelbrain.public_bundle import PublicBundleError
        with tempfile.TemporaryDirectory() as root:
            cookie=Path(root)/'cookies.txt';cookie.write_text('sensitive')
            os.chmod(cookie,0o644)
            with self.assertRaises(PublicBundleError):
                acquire_public_bundle('https://instagram.com/p/EXAMPLE123/',Path(root),
                                      cookies_file=cookie)
    def test_session_created_from_secret_private_and_deleted(self):
        from reelbrain.session_cookies import temporary_instagram_cookies
        with patch.dict(os.environ,{'REELBRAIN_INSTAGRAM_COOKIES_B64':base64.b64encode(
                b'# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\ttesttoken\n').decode()}):
            with temporary_instagram_cookies() as cookie:
                self.assertIsNotNone(cookie)
                p=Path(cookie)
                self.assertTrue(p.exists())
                self.assertEqual(p.stat().st_mode & 0o077,0)
            self.assertFalse(p.exists())
    def test_no_cookie_secret_is_no_op(self):
        from reelbrain.session_cookies import temporary_instagram_cookies
        with patch.dict(os.environ,{'REELBRAIN_INSTAGRAM_COOKIES_B64':''}):
            with temporary_instagram_cookies() as path:
                self.assertIsNone(path)


if __name__ == '__main__':
    unittest.main()
