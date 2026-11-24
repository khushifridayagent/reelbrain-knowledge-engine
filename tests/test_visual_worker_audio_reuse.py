"""Keep independently saved hosted speech intact; do not run redundant ASR."""
import unittest
from unittest.mock import patch
from reelbrain.durable_worker import reusable_hosted_audio
from reelbrain.media_evidence_summary import build_media_summary

class Cursor:
    def __init__(self,row):self.row=row
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,query,params):self.params=params
    def fetchone(self):return self.row

class DB:
    def __init__(self,row):self.cur=Cursor(row)
    def cursor(self):return self.cur

URL='https://www.instagram.com/reel/DgGHCjZIZtW/'
VALID={'provider':'transcriptfetch','source_type':'third_party_asr_by_reel_url',
       'text':'Existing speech','segments':[{'start':0,'end':1,'text':'Existing speech'}]}

class StoredSpeechTests(unittest.TestCase):
    def test_reuses_only_valid_saved_speech_for_exact_source(self):
        pg=DB((VALID,))
        self.assertEqual(reusable_hosted_audio(pg,URL),'transcriptfetch')
        self.assertEqual(pg.cur.params,(URL,))
    def test_empty_or_invalid_transcript_keeps_local_asr_available(self):
        for row in (None,({},),({**VALID,'text':' '},),({**VALID,'segments':[]},),
                    ({**VALID,'provider':'unknown'},),({**VALID,'source_type':'caption'},)):
            with self.subTest(row=row):
                self.assertIsNone(reusable_hosted_audio(DB(row),URL))
    def test_reused_hosted_speech_not_mislabeled_as_local_source_audio(self):
        result=build_media_summary(
            [{'kind':'ocr','locator':'00:01','verbatim':'Visible text'}],
            {'media_processed':True,'stage_observations':{'ocr':1},'hosted_audio_reused':'transcriptfetch'})
        self.assertFalse(result['audio_transcribed'])
        self.assertEqual(result['content']['hosted_audio_reused'],'transcriptfetch')
        self.assertTrue(result['ocr_analyzed'])


    def test_production_visual_engine_does_not_retranscribe_existing_speech(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from reelbrain.public_bundle import PublicBundle
        from reelbrain.durable_worker import process_url
        with TemporaryDirectory() as d:
            path=Path(d)/'fixture.mp4'
            path.write_bytes(b'fixture')
            for row,expect_reuse in [((VALID,),True),(None,False)]:
                with self.subTest(reuse=expect_reuse), patch.dict('os.environ',{'REELBRAIN_ENABLE_LOCAL_ASR':'1'},clear=True):
                    with patch('reelbrain.scrapecreators_media.acquire_with_public_provider',return_value=PublicBundle((path,),'fixture')), \
                         patch('reelbrain.durable_worker.LocalPipelineEngine') as engine, \
                         patch('reelbrain.local_asr.FasterWhisperSpeechToText') as local_asr, \
                         patch('reelbrain.durable_worker.save_reel_to_postgres',return_value={'persisted_in_postgres':True}) as writer:
                        engine.return_value.ingest.return_value={'processing_receipt_id':'fixture','status':'partial'}
                        result=process_url(URL,DB(row),apify_token='',acquisition='yt_dlp_public')
                        self.assertTrue(result['persisted_in_postgres'])
                        if expect_reuse:
                            local_asr.assert_not_called()
                            self.assertIsNone(engine.call_args.kwargs['audio_model'])
                            self.assertEqual(writer.call_args.args[-1]['hosted_audio_reused'],'transcriptfetch')
                        else:
                            local_asr.assert_called_once()
                            self.assertIs(engine.call_args.kwargs['audio_model'],local_asr.return_value)

if __name__=='__main__':unittest.main()
