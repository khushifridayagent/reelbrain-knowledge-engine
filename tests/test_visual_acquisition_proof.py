import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from reelbrain.public_bundle import acquire_public_bundle, PublicBundleError
from reelbrain.public_media import PublicMediaError
from reelbrain.meta_business_media import acquire_meta_bundle, MetaMediaUnavailable
from test_meta_business_media import FakeClient, response_for, SRC

class VisualAcquisitionProof(unittest.TestCase):
    def test_gallery_poster_is_not_a_complete_reel(self):
        def yt_fail(*args,**kwargs):
            raise PublicMediaError('Public Reel download unavailable: http_forbidden')
        from unittest.mock import patch
        def gallery(argv,**kw):
            folder=Path(argv[argv.index('-D')+1])
            (folder/'poster.jpg').write_bytes(bytes.fromhex('ffd8ff')+b'X'*100)
            return SimpleNamespace(returncode=0,stderr='')
        with tempfile.TemporaryDirectory() as d:
            with patch('reelbrain.public_bundle.acquire_public_reel',side_effect=yt_fail):
                with self.assertRaisesRegex(PublicBundleError,'reel_original_video_missing'):
                    acquire_public_bundle(SRC,d,gallery_runner=gallery)

    def test_invalid_current_file_is_removed_even_if_download_fails_validation(self):
        class Stream:
            status_code=200
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def iter_bytes(self,chunk_size=1024):yield b'not an mp4'*30
        class Download:
            def stream(self,*args,**kwargs):return Stream()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(MetaMediaUnavailable,'invalid media bytes'):
                acquire_meta_bundle(SRC,'aimortal.ig','fixture','17841400001234567',d,
                    lookup_http=FakeClient(response_for()),download_http=Download())
            self.assertEqual(list(Path(d).iterdir()),[])

if __name__=='__main__':unittest.main()
