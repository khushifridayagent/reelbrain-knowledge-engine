"""Regression guards for independently failing stages; no live services."""
import io
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock

from reelbrain.hosted_transcript_job import _reserve_one
from reelbrain.meta_business_media import (
    MetaSourceAsset, MetaMediaUnavailable, download_source_assets,
)

class ReservationCursor:
    def __init__(self, source): self.source=source; self.sql=[]; self.n=0
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def execute(self,sql,args=None): self.sql.append((sql,args))
    def fetchone(self):
        self.n+=1
        return (self.source,) if self.n==1 else (1,)

class ReservationDB:
    def __init__(self, source): self.cur=ReservationCursor(source)
    def transaction(self): return nullcontext()
    def cursor(self): return self.cur

class Stream:
    status_code=200
    headers={}
    def __init__(self,data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*a): return False
    def iter_bytes(self,chunk_size): yield self.data

class CDN:
    def __init__(self,images): self.images=iter(images)
    def stream(self,*a,**k): return Stream(next(self.images))

def image_bytes(fmt):
    from PIL import Image
    out=io.BytesIO()
    Image.new('RGB',(12,12),(30,60,90)).save(out,format=fmt)
    return out.getvalue()

class ReliabilityHardeningTests(unittest.TestCase):
    def test_hosted_speech_never_reserves_post_or_charges_budget(self):
        for source in ('https://www.instagram.com/p/Fixture123/',
                       'https://example.com/reel/Fixture123/'):
            with self.subTest(source=source):
                db=ReservationDB(source)
                self.assertIsNone(_reserve_one(db,'transcriptfetch'))
                self.assertEqual(len(db.cur.sql),2)
                self.assertIn("source_url ~",db.cur.sql[1][0])
                self.assertNotIn('INSERT INTO',db.cur.sql[-1][0])

    def test_hosted_speech_still_reserves_exact_reel(self):
        source='https://www.instagram.com/reel/Fixture123/'
        db=ReservationDB(source)
        self.assertEqual(_reserve_one(db,'transcriptfetch'),source)
        self.assertEqual(len(db.cur.sql),4)

    def test_original_png_webp_jpeg_assets_preserve_order(self):
        assets=tuple(MetaSourceAsset('IMAGE',f'https://scontent.cdninstagram.com/{i}.jpg')
                     for i in range(3))
        with tempfile.TemporaryDirectory() as td:
            b=download_source_assets(assets,td,download_http=CDN(
                [image_bytes('PNG'),image_bytes('WEBP'),image_bytes('JPEG')]))
            self.assertEqual([p.name for p in b.paths],
                             ['page_01.png','page_02.webp','page_03.jpg'])
            self.assertEqual(len(b.paths),3)

    def test_invalid_media_never_becomes_valid_or_leaves_partial_bundle(self):
        assets=(MetaSourceAsset('IMAGE','https://scontent.cdninstagram.com/a.jpg'),
                MetaSourceAsset('IMAGE','https://scontent.cdninstagram.com/b.jpg'))
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(MetaMediaUnavailable):
                download_source_assets(assets,td,download_http=CDN(
                    [image_bytes('PNG'),b'<html>not an image</html>'*4]))
            self.assertEqual(list(Path(td).iterdir()),[])
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(MetaMediaUnavailable):
                download_source_assets((MetaSourceAsset('VIDEO',assets[0].media_url),),
                    td,download_http=CDN([image_bytes('PNG')]))
            self.assertEqual(list(Path(td).iterdir()),[])

    def test_optional_speech_failure_does_not_block_core_workflow(self):
        yml=(Path(__file__).resolve().parents[1]/'.github/workflows/reelbrain-media-batch.yml').read_text()
        step=yml.split('- name: URL-first speech transcript',1)[1].split('- name:',1)[0]
        self.assertIn('continue-on-error: true',step)
        self.assertIn('timeout-minutes: 5',step)
        self.assertIn('steps.optional_speech.outcome',yml)
        self.assertIn('::warning::Optional hosted speech',yml)

    def test_missing_required_db_configuration_is_not_green(self):
        yml=(Path(__file__).resolve().parents[1]/'.github/workflows/reelbrain-media-batch.yml').read_text()
        step=yml.split('- name: Detect dedicated DB secret',1)[1].split('- uses:',1)[0]
        self.assertIn('::error::REELBRAIN_DB_URL',step)
        self.assertIn('exit 1',step)

    def test_coordinator_recovers_crashed_final_attempt_without_dead_letter(self):
        sql=(Path(__file__).resolve().parents[1]/'sql/0035_recover_expired_media_leases.sql').read_text()
        self.assertIn("status='queued'",sql)
        self.assertIn('attempts=greatest(0,attempts-1)',sql)
        self.assertIn("status='leased' and lease_until<now()",sql)
        self.assertIn('for update skip locked',sql.lower())
        self.assertNotIn("status='dead_letter'",sql)

if __name__=='__main__': unittest.main()
