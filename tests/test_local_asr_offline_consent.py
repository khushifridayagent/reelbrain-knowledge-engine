"""Regression: private, local CPU transcription must not require remote uploads."""
import tempfile
import unittest
from pathlib import Path

from reelbrain.contracts import Observation
from reelbrain.engine import LocalPipelineEngine, RemoteConsentRequired
from reelbrain.store import KnowledgeStore


class LocalSpeech:
    requires_external = False
    def transcribe(self, audio):
        return [Observation('The source speaks about on-device OCR.',kind='asr',locator='1.00-2.00')]


class RemoteSpeech:
    def transcribe(self, audio):
        raise AssertionError('Remote API should not be called without opt-in')


class ConsentTests(unittest.TestCase):
    def test_local_whisper_is_allowed_offline(self):
        with tempfile.TemporaryDirectory() as d:
            media=Path(d)/'sample.mp4';media.write_bytes(b'fake-media-fixture')
            store=KnowledgeStore(Path(d)/'db.sqlite')
            try:
                engine=LocalPipelineEngine(store,ocr=lambda p:[],audio_model=LocalSpeech(),
                                          audio_extractor=lambda p:p)
                result=engine.ingest(media,'https://instagram.com/reel/Source111/',allow_external=False)
                self.assertEqual(result['stage_observations']['asr'],1)
                self.assertEqual(result['external_calls'],0)
                self.assertEqual(result['status'],'evidence_saved')
            finally:
                store.close()

    def test_remote_transcription_still_requires_external_upload_opt_in(self):
        with tempfile.TemporaryDirectory() as d:
            media=Path(d)/'sample.mp4';media.write_bytes(b'fake-media-fixture')
            store=KnowledgeStore(Path(d)/'db.sqlite')
            try:
                engine=LocalPipelineEngine(store,ocr=lambda p:[],audio_model=RemoteSpeech(),
                                          audio_extractor=lambda p:p)
                with self.assertRaises(RemoteConsentRequired):
                    engine.ingest(media,'https://instagram.com/reel/Source111/',allow_external=False)
            finally:
                store.close()

    def test_local_adapter_declares_no_remote_calls(self):
        from reelbrain.local_asr import FasterWhisperSpeechToText
        self.assertIs(FasterWhisperSpeechToText.requires_external,False)


if __name__=='__main__':
    unittest.main()
