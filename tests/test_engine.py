import tempfile,unittest
from pathlib import Path
from reelbrain.store import KnowledgeStore
from reelbrain.contracts import Observation

class FakeAudio:
    def transcribe(self,path):
        return [Observation('The tutorial shows https://github.com/onyx-dot-app/onyx for search.',kind='asr',locator='00:01')]

class FakeVideo:
    def analyze(self,path):
        # The model can hallucinate links: this record is never exact source proof.
        return [Observation('https://github.com/definitely-unreal/faked',kind='model_inference',locator='00:02')]

class PipelineEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=KnowledgeStore(Path(self.tmp.name)/'engine.db')
        self.media=Path(self.tmp.name)/'safe.mp4';self.media.write_bytes(b'not a real video: tests inject OCR')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_default_does_not_use_any_external_models(self):
        from reelbrain.engine import LocalPipelineEngine
        calls=[]
        engine=LocalPipelineEngine(self.db,ocr=lambda path:(calls.append('ocr') or [Observation('See https://github.com/onyx-dot-app/onyx',kind='ocr',locator='00:01')]))
        output=engine.ingest(media_path=self.media,source_url='https://instagram.com/reel/AbCd01/',tenant='isolated')
        self.assertEqual(calls,['ocr'])
        self.assertEqual(output['resource_count'],1)
        self.assertEqual(output['external_calls'],0)
        self.assertEqual(output['status'],'evidence_saved')
    def test_consent_gate_prevents_paid_model_calls(self):
        from reelbrain.engine import LocalPipelineEngine,RemoteConsentRequired
        engine=LocalPipelineEngine(self.db,ocr=lambda _ : [],audio_model=FakeAudio(),video_model=FakeVideo(),audio_extractor=lambda p:p)
        with self.assertRaises(RemoteConsentRequired):
            engine.ingest(media_path=self.media,source_url='https://instagram.com/reel/AbCd01/',tenant='isolated')
    def test_partial_success_and_hallucination_gate(self):
        from reelbrain.engine import LocalPipelineEngine
        def failing_ocr(_):raise ValueError('Tesseract unavailable')
        engine=LocalPipelineEngine(self.db,ocr=failing_ocr,audio_model=FakeAudio(),video_model=FakeVideo(),audio_extractor=lambda p:p)
        output=engine.ingest(media_path=self.media,source_url='https://instagram.com/reel/AbCd01/',tenant='isolated',allow_external=True)
        self.assertEqual(output['status'],'partial')
        self.assertIn('ocr',output['stage_errors'])
        self.assertEqual(output['resource_count'],1)
        self.assertEqual(self.db.counts('isolated')['resources'],1)
        self.assertEqual(self.db.search('faked',tenant='isolated'),[])
        self.assertEqual(output['external_calls'],2)
    def test_media_input_path_must_be_real_file(self):
        from reelbrain.engine import LocalPipelineEngine
        engine=LocalPipelineEngine(self.db,ocr=lambda _:[])
        with self.assertRaises(FileNotFoundError):
            engine.ingest(Path(self.tmp.name)/'fake.mp4','https://instagram.com/reel/test1/',tenant='isolated')

class MockFactAgent:
    def extract(self,observations,supported_urls):
        from reelbrain.profiles import EvidenceClaim
        direct=next(e for e in observations if e.kind=='asr')
        return [EvidenceClaim('https://github.com/onyx-dot-app/onyx','use_case','search','%s'%direct.uid,'search')],[]

class DeepAgentIntegration(unittest.TestCase):
    def test_fact_agent_triggered_with_grounded_observations(self):
        from reelbrain.engine import LocalPipelineEngine
        with tempfile.TemporaryDirectory() as d:
            db=KnowledgeStore(Path(d)/'deep.db')
            try:
                p=Path(d)/'clip.mp4';p.write_bytes(b'video under mock')
                engine=LocalPipelineEngine(db,ocr=lambda _:[],audio_model=FakeAudio(),fact_model=MockFactAgent(),audio_extractor=lambda p:p)
                result=engine.ingest(p,'https://www.instagram.com/reel/RepRepo1/',tenant='research',allow_external=True)
                self.assertEqual(result['facts_accepted'],1)
                self.assertEqual(result['external_calls'],2)
                self.assertIn('use_case',str(db.search('onyx',tenant='research')[0]['facts']))
            finally:db.close()

    def test_optional_enrichment_failure_does_not_block_complete_media(self):
        from reelbrain.engine import LocalPipelineEngine
        from reelbrain.media_evidence_summary import build_media_summary
        class BrokenEnrichment:
            def extract(self,observations,supported_urls):raise RuntimeError('optional unavailable')
        with tempfile.TemporaryDirectory() as d:
            db=KnowledgeStore(Path(d)/'deep.db')
            try:
                p=Path(d)/'clip.png';p.write_bytes(b'fixture')
                engine=LocalPipelineEngine(db,ocr=lambda _:[Observation('Visible workflow: install, configure, run',kind='ocr')],video_model=FakeVideo(),fact_model=BrokenEnrichment())
                result=engine.ingest(p,'https://instagram.com/p/Repo123/',allow_external=True)
                self.assertEqual(result['status'],'evidence_saved')
                self.assertNotIn('fact_enrichment',result['stage_errors'])
                self.assertIn('fact_enrichment',result['optional_stage_errors'])
                self.assertEqual(build_media_summary([{'kind':'ocr','verbatim':'workflow','locator':'image:1'}],{**result,'media_processed':True})['processing_stage'],'completed')
            finally:db.close()
