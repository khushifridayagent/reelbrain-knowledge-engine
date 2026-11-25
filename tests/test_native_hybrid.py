import unittest
from pathlib import Path
import numpy as np
from reelbrain.native_hybrid import Frame, inspect_frames, NativeInspectionPending, GeminiInlineVision, HybridVision
from reelbrain.contracts import Observation

class Cache:
    def __init__(self): self.data={}
    def load(self,stage,*,unit=None): return self.data.get((stage,unit))
    def save(self,stage,events,elapsed,*,unit=None): self.data[stage,unit]=(events,elapsed)

class NativeHybridTests(unittest.TestCase):
    def test_single_frame_and_exact_duplicate_resume(self):
        a=np.zeros((32,32,3),np.uint8); b=a.copy(); b[1,1]=[0,0,255]
        frames=[Frame(0,0,a),Frame(1,16.67,b),Frame(2,33.33,a)]
        calls=[]
        def read(pixels):
            calls.append(pixels.copy())
            return [Observation('https://example.org/single' if np.array_equal(pixels,b) else 'background',kind='ocr')]
        cache=Cache()
        with self.assertRaises(NativeInspectionPending):
            inspect_frames(iter(frames),read,expected_frames=3,checkpoint=cache,chunk_size=2,max_new_chunks=1)
        result=inspect_frames(iter(frames),read,expected_frames=3,checkpoint=cache,chunk_size=2,max_new_chunks=1)
        self.assertEqual(len(calls),2)
        self.assertEqual(len(result),2)
        self.assertTrue(any('single' in x.text and 'frame:1' in x.locator for x in result))
    def test_truncated_video_cannot_be_complete(self):
        a=np.zeros((4,4,3),np.uint8)
        with self.assertRaises(NativeInspectionPending):
            inspect_frames([Frame(0,0,a)],lambda p:[],expected_frames=2)
    def test_failed_ocr_is_not_cached(self):
        cache=Cache(); a=np.zeros((4,4,3),np.uint8)
        def fail(p): raise RuntimeError('fixture failure')
        with self.assertRaises(NativeInspectionPending):
            inspect_frames([Frame(0,0,a)],fail,expected_frames=1,checkpoint=cache)
        self.assertEqual(cache.data,{})
    def test_gemini_parser_rejects_truncated_and_empty_output(self):
        for payload in (
            {'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{"observations":[]}'}]}}]},
            {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"observations":[]}'}]}}]},
        ):
            with self.assertRaises(RuntimeError): GeminiInlineVision.parse(payload)
    def test_gemini_output_remains_inference(self):
        payload={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"observations":[{"timestamp":"00:01","description":"workflow shown"}]}'}]}}]}
        self.assertEqual(GeminiInlineVision.parse(payload)[0].kind,'model_inference')
    def test_hybrid_fallback_and_checkpoint_reuse(self):
        class Broken:
            def analyze(self,p): raise RuntimeError('quota')
        class Good:
            def __init__(self): self.calls=0
            def analyze(self,p): self.calls+=1; return [Observation('screen',kind='model_inference')]
        cache=Cache(); good=Good()
        h=HybridVision(Broken(),good)
        self.assertEqual(h.analyze(Path('fixture.mp4'),checkpoint=cache,asset_index=1)[0].text,'screen')
        h.analyze(Path('fixture.mp4'),checkpoint=cache,asset_index=1)
        self.assertEqual(good.calls,1)
