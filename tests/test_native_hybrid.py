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

    def test_local_whisper_fallback_on_groq_failure(self):
        from reelbrain.native_hybrid import SpeechFallback
        class Broken:
            def transcribe(self,p):raise RuntimeError('quota')
        class Local:
            def transcribe(self,p):return [Observation('spoken',kind='asr')]
        self.assertEqual(SpeechFallback(Broken(),Local()).transcribe(Path('fixture.wav'))[0].text,'spoken')

    def test_partial_native_evidence_is_preserved_and_legacy_cache_not_reused(self):
        from tempfile import TemporaryDirectory
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.store import KnowledgeStore
        class Partial:
            def analyze(self,path,**kw):
                raise NativeInspectionPending('coverage pending',[Observation('new exact native text',kind='ocr',locator='frame:1@16.67ms')])
        with TemporaryDirectory() as d:
            p=Path(d)/'fixture.png';p.write_bytes(b'fixture')
            cache=Cache();cache.save('ocr',[Observation('old sampled text',kind='ocr')],1)
            db=KnowledgeStore(Path(d)/'local.db')
            try:
                r=LocalPipelineEngine(db,native_ocr=Partial()).ingest(p,'https://instagram.com/reel/Native123/',checkpoint=cache)
                self.assertEqual(r['status'],'partial')
                self.assertIn('ocr',r['stage_errors'])
                self.assertEqual(r['stage_observations']['ocr'],1)
                text=db.con.execute('select verbatim from evidence where source_id=?',(r['source_id'],)).fetchall()
                self.assertEqual([x['verbatim'] for x in text],['new exact native text'])
            finally:db.close()

    def test_actual_lossless_native_single_frame_url(self):
        from tempfile import TemporaryDirectory
        import subprocess
        from PIL import Image,ImageDraw,ImageFont
        from reelbrain.native_hybrid import NativeOCR
        with TemporaryDirectory() as d:
            root=Path(d)
            for index in range(4):
                im=Image.new('RGB',(960,360),'white')
                if index==1:
                    draw=ImageDraw.Draw(im)
                    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',48)
                    draw.text((24,130),'https://example.org/rb7',font=font,fill='black')
                im.save(root/f'{index:03}.png')
            path=root/'fixture.mkv'
            subprocess.run(['ffmpeg','-v','error','-y','-framerate','60','-i',str(root/'%03d.png'),'-c:v','ffv1',str(path)],check=True,capture_output=True,timeout=15)
            cache=Cache()
            result=NativeOCR(max_seconds=90).analyze(path,checkpoint=cache)
            self.assertTrue(any('https://example.org/rb7' in x.text and 'frame:1@' in x.locator for x in result))
            import json
            manifests=[json.loads(e.text) for events,_ in cache.data.values() for e in events if e.kind=='native_manifest']
            self.assertEqual(sum(len(m) for m in manifests),4)

    def test_parallel_native_inspection_preserves_exact_order_and_dedup(self):
        a=np.zeros((4,4,3),np.uint8); b=a.copy();b[1,1]=[1,2,3]
        c=b.copy();c[2,2]=[4,5,6]
        frames=[Frame(0,0,a),Frame(1,16,b),Frame(2,32,a),Frame(3,48,c)]
        def read(p):return [Observation(str(int(p.sum())),kind='ocr')]
        expected=inspect_frames(frames,read,expected_frames=4,parallelism=1)
        actual=inspect_frames(frames,read,expected_frames=4,parallelism=2)
        self.assertEqual(actual,expected)

    def test_progress_yield_does_not_restart_on_other_provider(self):
        from reelbrain.qwen_vl import QwenPartialVisualError
        class Progress:
            def analyze(self,p):
                raise QwenPartialVisualError('visual coverage pending',[Observation('done',kind='model_inference')])
        class Never:
            def analyze(self,p):raise AssertionError('fallback would repeat work')
        with self.assertRaises(QwenPartialVisualError) as e:
            HybridVision(Progress(),Never()).analyze(Path('sample.mp4'))
        self.assertEqual(e.exception.partial_observations[0].text,'done')

    def test_native_progress_retries_in_15_minutes_without_quota_reset(self):
        from reelbrain.resumable_media import retry_seconds
        self.assertEqual(retry_seconds({'ocr':'NativeInspectionPending: native OCR incomplete; resume saved chunks'}),900)
        self.assertEqual(retry_seconds({'vlm':'visual coverage pending: resume checkpointed batches'}),900)

    def test_hybrid_rate_limit_does_not_assume_cloudflare_midnight(self):
        from reelbrain.model_quota_retry import model_quota_retry_seconds
        from datetime import datetime,timezone
        self.assertEqual(model_quota_retry_seconds({'vlm':'hybrid provider rate limit; retry later'},now=datetime(2026,11,25,10,tzinfo=timezone.utc)),900)

    def test_native_url_disagreement_is_retained_but_not_promoted(self):
        from reelbrain.native_hybrid import reconcile_ocr_reads
        from reelbrain.contracts import candidate_urls,evidence_filter
        readings=reconcile_ocr_reads(['https://example.org/rb1','https://example.org/rbl','https://example.org/rb1'],[])
        self.assertTrue(any(e.kind=='ocr' and 'rb1' in e.text for e in readings))
        self.assertTrue(any(e.kind=='ocr_uncertain' and 'rbl' in e.text for e in readings))
        candidates=[c for e in readings for c in candidate_urls(e.text)]
        outcome=evidence_filter(candidates,readings)
        self.assertEqual({x.url for x in outcome.accepted},{'https://example.org/rb1'})

    def test_silent_video_can_complete_without_fabricated_asr(self):
        from reelbrain.media_evidence_summary import build_media_summary
        r={'media_processed':True,'status':'evidence_saved','stage_observations':{'ocr':1,'vlm':1},'stage_errors':{},'audio_required':False,'unattempted_modalities':['asr']}
        observations=[{'kind':'ocr','verbatim':'test','locator':'frame:0'}]
        self.assertEqual(build_media_summary(observations,r)['processing_stage'],'completed')
        self.assertFalse(build_media_summary(observations,r)['audio_transcribed'])

    def test_native_audio_stream_detection_is_fail_closed(self):
        from tempfile import TemporaryDirectory
        import subprocess
        from reelbrain.native_hybrid import has_audio_stream
        with TemporaryDirectory() as d:
            p=Path(d)/'silent.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=white:s=64x64:d=0.2','-an','-c:v','libx264',str(p)],check=True,timeout=10)
            self.assertFalse(has_audio_stream(p))
            self.assertTrue(has_audio_stream(Path(d)/'missing.mp4'))

    def test_shared_provider_cooldown_skips_rate_limited_provider_on_next_reel(self):
        from reelbrain.qwen_vl import QwenPartialVisualError
        class SharedCache(Cache):
            def __init__(self):super().__init__();self.cooldowns={}
            def provider_delay(self,key):return self.cooldowns.get(key,0)
            def defer_provider(self,key,seconds):self.cooldowns[key]=seconds
        class Limited:
            cooldown_key='gemini_vision'
            def __init__(self):self.calls=0
            def analyze(self,p):self.calls+=1;raise RuntimeError('Gemini quota exceeded')
        class Backup:
            cooldown_key='groq_vision'
            def analyze(self,p):return [Observation('backup',kind='model_inference')]
        cache=SharedCache();limited=Limited()
        for asset in (1,2):
            self.assertEqual(HybridVision(limited,Backup()).analyze(Path('test.mp4'),checkpoint=cache,asset_index=asset)[0].text,'backup')
        self.assertEqual(limited.calls,1)
        self.assertGreaterEqual(cache.cooldowns['gemini_vision'],900)
    def test_cooldown_retry_uses_earliest_available_provider(self):
        from reelbrain.resumable_media import retry_seconds
        self.assertEqual(retry_seconds({'vlm':'QwenPartialVisualError: hybrid provider cooldown:1200'}),1200)
        self.assertEqual(retry_seconds({'vlm':'QwenPartialVisualError: hybrid provider cooldown:30'}),900)

    def test_gemini_large_video_segments_resume_without_repeat(self):
        from tempfile import TemporaryDirectory
        import subprocess
        from reelbrain.qwen_vl import QwenPartialVisualError
        class Probe(GeminiInlineVision):
            def __init__(self):
                super().__init__('fixture',segment_seconds=1,max_new_segments=1)
                self.calls=0
            def _inline(self,path):
                self.calls+=1
                self.assert_segment(path)
                return [Observation('visual fixture',kind='model_inference',locator='gemini:00:00')]
            def assert_segment(self,path):
                assert path.is_file() and path.stat().st_size>0
        with TemporaryDirectory() as d:
            p=Path(d)/'fixture.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=160x90:rate=10:duration=3',
                            '-an','-c:v','libx264',str(p)],check=True,timeout=20)
            cache=Cache();vision=Probe()
            for expected in (1,2):
                with self.assertRaises(QwenPartialVisualError) as e:
                    vision._analyze_segments(p,checkpoint=cache,asset_index=1)
                self.assertIn('coverage pending',str(e.exception))
                self.assertEqual(len(e.exception.partial_observations),expected)
            events=vision._analyze_segments(p,checkpoint=cache,asset_index=1)
            self.assertEqual(vision.calls,3)
            self.assertEqual(len(events),3)
            self.assertEqual(len({x.locator for x in events}),3)

    def test_focused_inspection_catches_single_frame_text_without_qr(self):
        from reelbrain.knowledge_focus import focused_candidates, focused_read
        from PIL import Image, ImageDraw, ImageFont
        from unittest.mock import patch
        from reelbrain.native_hybrid import Frame
        base=np.full((360,960,3),240,np.uint8)
        im=Image.fromarray(base.copy())
        ImageDraw.Draw(im).text((25,130),'https://example.org/rb7',font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',40),fill='black')
        changed=np.asarray(im).copy()
        frames=[Frame(i,i*1000/60,changed if i==17 else base) for i in range(60)]
        chosen=list(focused_candidates(frames))
        self.assertIn(17,[f.index for f in chosen])
        self.assertLess(len(chosen),10)
        with patch('cv2.QRCodeDetector',side_effect=AssertionError('QR must not run')):
            observations=focused_read(changed)
        self.assertTrue(any('https://example.org/rb7' in x.text for x in observations))
        self.assertTrue(all(x.kind in ('ocr','ocr_uncertain') for x in observations))

    def test_focused_duplicate_text_keeps_first_locator(self):
        from reelbrain.knowledge_focus import unique_knowledge
        rows=[Observation('same procedure',kind='ocr',locator='frame:1'),Observation('same procedure',kind='ocr',locator='frame:2'),Observation('new command',kind='ocr',locator='frame:3'),Observation('https://qr.example/old',kind='qr')]
        self.assertEqual([r.locator for r in unique_knowledge(rows)],['frame:1','frame:3'])

    def test_focused_default_finishes_more_than_64_chunks_without_dropping_frames(self):
        from reelbrain.knowledge_focus import FocusedOCR
        from reelbrain.native_hybrid import Frame
        from unittest.mock import patch
        from types import SimpleNamespace
        from contextlib import nullcontext
        from fractions import Fraction
        import numpy as np
        pixels=np.zeros((8,8,3),np.uint8)
        class Decoded:
            time_base=Fraction(1,60)
            def __init__(self,i):self.pts=i
            def to_ndarray(self,format):
                a=pixels.copy();a[0,0]=[self.pts%256,self.pts//256,0];return a
        video=SimpleNamespace(frames=520)
        container=SimpleNamespace(streams=SimpleNamespace(video=[video]),decode=lambda _: (Decoded(i) for i in range(520)))
        with patch('av.open',return_value=nullcontext(container)),patch('reelbrain.knowledge_focus.focused_candidates',side_effect=lambda frames:iter(frames)),patch('reelbrain.knowledge_focus.focused_read',return_value=[Observation('visible technical instruction',kind='ocr')]) as ocr:
            cache=Cache()
            result=FocusedOCR().analyze(Path('fixture.mp4'),checkpoint=cache,asset_index=1)
            self.assertEqual(ocr.call_count,520)
            self.assertEqual(len(cache.data),65)
            self.assertEqual(len(result),1)
            FocusedOCR().analyze(Path('fixture.mp4'),checkpoint=cache,asset_index=1)
            self.assertEqual(ocr.call_count,520)

    def test_exact_duplicate_frames_do_not_repeat_ocr_and_code_indentation_survives(self):
        from reelbrain.knowledge_focus import FocusedOCR,unique_knowledge
        from unittest.mock import patch
        from types import SimpleNamespace
        from contextlib import nullcontext
        from fractions import Fraction
        a=np.zeros((8,8,3),np.uint8);b=a.copy();b[0,0]=[0,0,1]
        class Decoded:
            time_base=Fraction(1,60)
            def __init__(self,i):self.pts=i
            def to_ndarray(self,format):return b if self.pts==9 else a
        v=SimpleNamespace(frames=24)
        c=SimpleNamespace(streams=SimpleNamespace(video=[v]),decode=lambda _: (Decoded(i) for i in range(24)))
        def recognize(pixels):
            return [Observation('if ready:\n    run()' if np.array_equal(pixels,a) else 'if ready:\nrun()',kind='ocr')]
        with patch('av.open',return_value=nullcontext(c)),patch('reelbrain.knowledge_focus.focused_candidates',side_effect=lambda f:iter(f)),patch('reelbrain.knowledge_focus.focused_read',side_effect=recognize) as reader:
            rows=FocusedOCR().analyze(Path('fixture.mp4'),checkpoint=Cache(),asset_index=1)
            self.assertEqual(reader.call_count,2)
            self.assertEqual(len(rows),2)
            self.assertTrue(any(x.locator.startswith('frame:9@') for x in rows))
