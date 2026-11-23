import unittest,tempfile
from pathlib import Path
from types import SimpleNamespace
from reelbrain.contracts import evidence_filter,ResourceCandidate

class FakeFiles:
    def __init__(self):self.uploaded=[];self.deleted=[]
    def upload(self,file):self.uploaded.append(file);return SimpleNamespace(name='files/mock',uri='mock:video',mime_type='video/mp4',state=SimpleNamespace(name='ACTIVE'))
    def delete(self,name):self.deleted.append(name)

class FakeInteractions:
    def __init__(self,reply):self.reply=reply;self.calls=[]
    def create(self,**kwargs):self.calls.append(kwargs);return SimpleNamespace(output_text=self.reply)

class ProviderContractTests(unittest.TestCase):
    def test_gemini_video_proposals_never_become_primary_link_evidence(self):
        from reelbrain.providers import GeminiVideoResearcher
        files=FakeFiles();interactions=FakeInteractions('{"observations":[{"timestamp":"00:03","description":"fake repo https://github.com/fakeowner/unseenrepo"}]}')
        api=SimpleNamespace(files=files,interactions=interactions)
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'sample.mp4';file.write_bytes(b'fake mp4')
            obs=GeminiVideoResearcher(api_key='test',model='gemini-3.6-flash',client=api).analyze(file)
            self.assertEqual(len(obs),1)
            self.assertEqual(obs[0].kind,'model_inference')
            self.assertEqual(files.uploaded,[str(file)])
            self.assertEqual(files.deleted,['files/mock'])
            verdict=evidence_filter([ResourceCandidate('Fake','https://github.com/fakeowner/unseenrepo')],obs)
            self.assertEqual(len(verdict.accepted),0)
            self.assertEqual(interactions.calls[0]['model'],'gemini-3.6-flash')
    def test_gemini_failed_file_rejected_not_infinite_poll(self):
        from reelbrain.providers import GeminiVideoResearcher,ProviderError
        deleted=[]
        api=SimpleNamespace(files=SimpleNamespace(upload=lambda file:SimpleNamespace(name='files/bad',uri='bad',mime_type='video/mp4',state=SimpleNamespace(name='FAILED')),delete=lambda name:deleted.append(name)),interactions=FakeInteractions('x'))
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'clip.mp4';f.write_bytes(b'a')
            with self.assertRaises(ProviderError):GeminiVideoResearcher(api_key='test',client=api).analyze(f)
            self.assertEqual(deleted,['files/bad'])
