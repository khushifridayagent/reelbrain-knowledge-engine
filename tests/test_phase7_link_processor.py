"""TDD acceptance tests: explicit consent, single bounded provider run, no media claim on failure."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock
from reelbrain.acquire_apify import AcquiredPost,AcquisitionError
from reelbrain.link_processor import LinkProcessingOptions,process_instagram_link
from reelbrain.store import KnowledgeStore

URL='https://www.instagram.com/reel/Abc321/'

class LinkProcessorTests(unittest.TestCase):
 def setUp(self):
  self.d=tempfile.TemporaryDirectory()
  self.db=KnowledgeStore(Path(self.d.name)/'a.sqlite')
 def tearDown(self):self.db.close();self.d.cleanup()
 def options(self,**kwargs):
  base={'allow_paid':True,'allow_external':True,'rights_confirmed':True}
  return LinkProcessingOptions(**(base|kwargs))
 def test_requires_rights_and_both_network_consents_before_any_network(self):
  api=Mock();loader=Mock()
  for kwargs in ({'allow_paid':False},{'allow_external':False},{'rights_confirmed':False}):
   with self.assertRaises(PermissionError):
    process_instagram_link(self.db,URL,options=self.options(**kwargs),apify_client=api,downloader=loader)
  api.inspect.assert_not_called();loader.download.assert_not_called()
 def test_metadata_only_persists_caption_but_never_marks_video_processed(self):
  api=Mock(inspect=Mock(return_value=AcquiredPost(URL,'Abc321','See https://github.com/onyx-dot-app/onyx',None)))
  loader=Mock()
  result=process_instagram_link(self.db,URL,options=self.options(),apify_client=api,downloader=loader)
  self.assertEqual(result['status'],'partial_metadata_only');self.assertFalse(result['media_processed'])
  self.assertEqual(result['resource_count'],1)
  self.assertEqual(result['provider_runs'],1)
  loader.download.assert_not_called()
 def test_successful_media_processing_receipt_preserves_evidence(self):
  api=Mock(inspect=Mock(return_value=AcquiredPost(URL,'Abc321','github.com/onyx-dot-app/onyx','https://video.fbcdn.net/video.mp4')))
  def download(url,destination):
   p=Path(destination);p.write_bytes(b'\x00\x00\x00\x18ftypisom'+b'0'*28);return p
  class FakeEngine:
   def ingest(self,media_path,source_url,tenant='personal',allow_external=False,extra_observations=None):
    self_assert.assertEqual(source_url,URL)
    self_assert.assertTrue(extra_observations)
    self_assert.assertEqual(extra_observations[0].locator,'apify:caption')
    return {'status':'evidence_saved','processing_receipt_id':'receipt-simulated','resource_count':1,'stage_errors':{},'stage_timings_ms':{'ocr':7}}
  self_assert=self
  result=process_instagram_link(self.db,URL,options=self.options(),apify_client=api,
      downloader=Mock(download=Mock(side_effect=download)),engine_factory=lambda store:FakeEngine())
  self.assertEqual(result['status'],'evidence_saved')
  self.assertTrue(result['media_processed']);self.assertEqual(result['provider_runs'],1)
  self.assertTrue(result['media_deleted_after_processing'])
 def test_download_failure_does_not_fabricate_completion_and_keeps_caption(self):
  api=Mock(inspect=Mock(return_value=AcquiredPost(URL,'Abc321','https://github.com/onyx-dot-app/onyx','https://video.fbcdn.net/video.mp4')))
  result=process_instagram_link(self.db,URL,options=self.options(),apify_client=api,
      downloader=Mock(download=Mock(side_effect=AcquisitionError('403 media unavailable'))))
  self.assertEqual(result['status'],'partial_metadata_only')
  self.assertFalse(result['media_processed'])
  self.assertEqual(result['resource_count'],1)
  self.assertEqual(result['media_error'],'AcquisitionError: 403 media unavailable')
 def test_video_url_spoofing_source_rejected_even_when_media_exists(self):
  api=Mock(inspect=Mock(return_value=AcquiredPost('https://www.instagram.com/reel/HACKED/','HACKED','caption','https://a.fbcdn.net/vid.mp4')))
  with self.assertRaises(AcquisitionError):
   process_instagram_link(self.db,URL,options=self.options(),apify_client=api,downloader=Mock())
