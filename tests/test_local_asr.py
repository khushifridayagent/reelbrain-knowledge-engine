"""Open-source CPU Whisper fallback with deterministic fake inference tests."""
import unittest
from pathlib import Path
from types import SimpleNamespace

class LocalASRTests(unittest.TestCase):
    def test_transcription_preserves_segment_timestamps(self):
        from reelbrain.local_asr import FasterWhisperSpeechToText
        class Stub:
            def transcribe(self,path,**kwargs):
                self.args=(path,kwargs)
                return iter([SimpleNamespace(text=' नमस्ते ',start=1.2,end=2.3),
                             SimpleNamespace(text='github.com/example/repo',start=3.0,end=4.2)]),{}
        model=Stub()
        adapter=FasterWhisperSpeechToText(model=model)
        result=adapter.transcribe(Path('/tmp/fake.wav'))
        self.assertEqual(len(result),2)
        self.assertEqual(result[0].kind,'asr')
        self.assertEqual(result[0].locator,'1.20-2.30')
        self.assertEqual(result[0].text,'नमस्ते')
        self.assertIn('vad_filter',model.args[1])
    def test_unrecognized_model_is_rejected_before_download(self):
        from reelbrain.local_asr import FasterWhisperSpeechToText
        with self.assertRaises(ValueError):
            FasterWhisperSpeechToText(model_size='hugemodel-remote')
if __name__=='__main__':unittest.main()
