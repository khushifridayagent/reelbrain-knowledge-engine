"""TranscriptFetch v2: URL first, exact Reel identity and durable async jobs."""
import unittest
from unittest.mock import patch

from reelbrain.transcriptfetch_api import (
    TranscriptFetchClient, TranscriptFetchError, normalize_transcriptfetch,
    validate_poll_id,
)


SOURCE='https://www.instagram.com/reel/DgGHCjZIZtW/'


class Reply:
    def __init__(self, body, code=200): self.body=body;self.status_code=code
    def json(self): return self.body
    def raise_for_status(self):
        if self.status_code>=400:raise RuntimeError('http error')


class HTTP:
    def __init__(self,post_res=None,get_res=None):self.post_res=post_res;self.get_res=get_res;self.calls=[]
    def post(self,url,**kw):
        self.calls.append(('post',url,kw))
        return self.post_res
    def get(self,url,**kw):
        self.calls.append(('get',url,kw))
        return self.get_res


def speech():
    return {'ok':True,'status':'completed','data':{
        'platform':'instagram','video_id':'DgGHCjZIZtW',
        'source':'audio','text':'A comprehensive verified transcript.',
        'segments':[{'start':0.25,'duration':2.4,'text':'A comprehensive verified transcript.'}]
    }}


class TranscriptFetchTests(unittest.TestCase):
    def test_reel_spoken_text_and_timestamp(self):
        found=normalize_transcriptfetch(SOURCE,speech())
        self.assertEqual(found['provider'],'transcriptfetch')
        self.assertEqual(found['text'],'A comprehensive verified transcript.')
        self.assertEqual(found['segments'][0]['end'],2.65)
        self.assertFalse(found['visual_frames_verified'])

    def test_respond_202_with_safe_job_id(self):
        h=HTTP(post_res=Reply({'ok':True,'status':'processing',
           'job_id':'asr_abc123','poll_url':'/api/v2/transcripts/jobs/asr_abc123'},202))
        a=TranscriptFetchClient('fixture',http=h).start(SOURCE)
        self.assertEqual(a['state'],'processing')
        self.assertEqual(a['job_id'],'asr_abc123')
        method,endpoint,params=h.calls[0]
        self.assertEqual(method,'post')
        self.assertEqual(endpoint,'https://transcriptfetch.com/api/v2/transcripts/video')
        self.assertEqual(params['json'],{'video':SOURCE,'mode':'audio','timestamps':True})
        self.assertEqual(params['headers']['Authorization'],'Bearer fixture')

    def test_poll_uses_fixed_endpoint_and_same_job_identifier(self):
        h=HTTP(get_res=Reply(speech()))
        a=TranscriptFetchClient('fixture',http=h).poll(SOURCE,'asr_abc123')
        self.assertEqual(a['state'],'completed')
        self.assertEqual(h.calls[0][1],'https://transcriptfetch.com/api/v2/transcripts/jobs/asr_abc123')

    def test_api_html_errors_do_not_leak_user_video(self):
        h=HTTP(post_res=Reply({'ok':False,'error':'secret third-party raw'},403))
        with self.assertRaises(TranscriptFetchError) as ctx:
            TranscriptFetchClient('fixture',http=h).start(SOURCE)
        self.assertNotIn('secret third-party',str(ctx.exception))
        self.assertNotIn('DgGHCjZIZtW',str(ctx.exception))

    def test_rejects_other_video_or_non_audio_captions(self):
        d=speech();d['data']['video_id']='WRONG_REEL'
        with self.assertRaises(TranscriptFetchError):
            normalize_transcriptfetch(SOURCE,d)
        d=speech();d['data']['source']='captions'
        with self.assertRaises(TranscriptFetchError):
            normalize_transcriptfetch(SOURCE,d)

    def test_official_timestamps_only_response_reconstructs_full_text(self):
        # Official TranscriptFetch SDK docs: with timestamps=true the REST
        # response may contain only segments; text is deliberately omitted.
        d=speech()
        d['data'].pop('text')
        d['data']['segments']=[
            {'start':0,'duration':1.5,'text':'Tool number one'},
            {'start':1.5,'duration':2.0,'text':'is available on GitHub'},
        ]
        found=normalize_transcriptfetch(SOURCE,d)
        self.assertIsNotNone(found)
        self.assertEqual(found['text'],'Tool number one is available on GitHub')
        self.assertEqual(len(found['segments']),2)

    def test_no_segments_and_no_text_returns_empty_not_complete(self):
        d=speech()
        d['data'].pop('text')
        d['data']['segments']=[]
        self.assertIsNone(normalize_transcriptfetch(SOURCE,d))

    def test_no_spoken_text_does_not_invent_knowledge(self):
        d=speech();d['data']['text']='';d['data']['segments']=[]
        self.assertIsNone(normalize_transcriptfetch(SOURCE,d))

    def test_disallow_poll_redirect_url_and_bad_ids(self):
        for jobid in ('../../env', 'https://evil.example/steal', 'asr_a?token=secret',''):
            with self.assertRaises(TranscriptFetchError):
                validate_poll_id(jobid)

    def test_disable_if_provider_not_selected_or_budget_unapproved(self):
        from reelbrain.hosted_transcript import hosted_transcript_enabled
        base={'REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER':'transcriptfetch',
              'TRANSCRIPTFETCH_API_KEY':'fixture',
              'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'1',
              'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'0'}
        with patch.dict('os.environ',base,clear=True):self.assertFalse(hosted_transcript_enabled())
        base['REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED']='1'
        with patch.dict('os.environ',base,clear=True):self.assertTrue(hosted_transcript_enabled())

if __name__=='__main__': unittest.main()
