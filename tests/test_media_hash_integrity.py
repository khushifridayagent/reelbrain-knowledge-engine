"""Real media bytes must be identifiable and persistent; partial replays must not erase good evidence."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from reelbrain.contracts import Observation
from reelbrain.engine import LocalPipelineEngine
from reelbrain.remote_reel_writer import RemoteWriteError, save_reel_to_postgres
from reelbrain.store import KnowledgeStore


class FakeCursor:
    def __init__(self,db):self.db=db
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,params):
        self.db.calls.append((sql,params))
    def executemany(self,sql,rows):
        self.db.batches.append((sql,list(rows)))
        for params in self.db.batches[-1][1]:self.execute(sql,params)


class FakePg:
    def __init__(self):self.calls=[];self.batches=[]
    def transaction(self):return self
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return FakeCursor(self)


class EvidencePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=KnowledgeStore(Path(self.temp.name)/'fixtures.db')
        self.media=Path(self.temp.name)/'file.mp4'
        self.media.write_bytes(b'synthetic-media-original-bytes')
        self.url='https://instagram.com/reel/EXAMPLE123/'
        self.engine=LocalPipelineEngine(self.store,ocr=lambda _: [
            Observation('https://github.com/onyx-dot-app/onyx',kind='ocr',locator='00:02')])
    def tearDown(self):self.store.close();self.temp.cleanup()

    def test_hash_is_derived_from_original_media_bytes(self):
        result=self.engine.ingest(self.media,self.url)
        self.assertEqual(result['media_sha256'],hashlib.sha256(self.media.read_bytes()).hexdigest())

    def test_remote_persistence_uses_non_null_sha_and_protects_prior_full_status(self):
        result=self.engine.ingest(self.media,self.url)
        result['media_processed']=True
        pg=FakePg()
        saved=save_reel_to_postgres(self.store,pg,self.url,result)
        self.assertTrue(saved['persisted_in_postgres'])
        insertion=next((sql,params) for sql,params in pg.calls if 'insert into reelbrain_research.reel_sources' in sql)
        self.assertEqual(insertion[1][3],hashlib.sha256(self.media.read_bytes()).hexdigest())
        self.assertIn('CASE',insertion[0].upper())
        self.assertEqual(len(pg.batches),2)
        self.assertEqual(len(pg.batches[0][1]),saved['observation_count'])
        self.assertEqual(len(pg.batches[1][1]),saved['resource_citations'])

    def test_bad_missing_hash_cannot_be_saved_as_verified_media(self):
        result=self.engine.ingest(self.media,self.url)
        result['media_sha256']=None
        with self.assertRaises(RemoteWriteError):
            save_reel_to_postgres(self.store,FakePg(),self.url,result)


if __name__=='__main__':
    unittest.main()
