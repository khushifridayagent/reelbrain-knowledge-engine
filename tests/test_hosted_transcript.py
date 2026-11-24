"""URL-first provider speech without writing or retaining original media."""
import unittest
from unittest.mock import patch

from reelbrain.hosted_transcript import (
    HostedTranscriptClient, TranscriptProviderError, normalize_transcript,
    hosted_transcript_enabled,
)


class Response:
    def __init__(self, data, status_code=200):
        self._data=data
        self.status_code=status_code
    def json(self):return self._data
    def raise_for_status(self):
        if self.status_code!=200:raise RuntimeError('upstream failed')


class HTTP:
    def __init__(self,data):
        self.data=data;self.requests=[]
    def get(self,url,**kwargs):
        self.requests.append((url,kwargs))
        return Response(self.data)


class HostedTranscriptTests(unittest.TestCase):
    def test_exact_shortcode_transcript_and_timestamp_segments(self):
        payload={'success':True,'credits_charged':1,'transcripts':[{
            'shortcode':'DgGHCjZIZtW',
            'text':'An AI CEO delegates tasks.',
            'transcript_with_timestamp':[{'start':0.2,'end':2.1,'text':'An AI CEO delegates tasks.'}]
        }]}
        result=normalize_transcript('https://www.instagram.com/reel/DgGHCjZIZtW/',payload)
        self.assertEqual(result['provider'],'scrapecreators')
        self.assertEqual(result['shortcode'],'DgGHCjZIZtW')
        self.assertEqual(result['text'],'An AI CEO delegates tasks.')
        self.assertEqual(result['segments'][0]['start'],0.2)
        self.assertFalse(result['first_party_media_verified'])

    def test_wrong_media_identity_refused(self):
        with self.assertRaises(TranscriptProviderError):
            normalize_transcript('https://instagram.com/reel/DgGHCjZIZtW/',
              {'success':True,'transcripts':[{'shortcode':'AnotherSource','text':'text'}]})

    def test_no_speech_returns_none_without_fabricating_video(self):
        self.assertIsNone(normalize_transcript('https://instagram.com/reel/DgGHCjZIZtW/',
              {'success':True,'transcripts':[{'shortcode':'DgGHCjZIZtW','text':None}]}))

    def test_unverified_timestamp_is_not_invented(self):
        result=normalize_transcript('https://instagram.com/reel/DgGHCjZIZtW/',
              {'success':True,'transcripts':[{'shortcode':'DgGHCjZIZtW','text':'Speech','transcript_with_timestamp':None}]})
        self.assertEqual(result['segments'],[])
        self.assertEqual(result['text'],'Speech')

    def test_api_receives_url_not_video_bytes_and_no_paid_long_mode(self):
        http=HTTP({'success':True,'transcripts':[{'shortcode':'DgGHCjZIZtW','text':'Speech'}]})
        client=HostedTranscriptClient(api_key='fixture-key',http=http)
        client.fetch('https://instagram.com/reel/DgGHCjZIZtW/')
        self.assertEqual(len(http.requests),1)
        endpoint,kwargs=http.requests[0]
        self.assertEqual(endpoint,'https://api.scrapecreators.com/v2/instagram/media/transcript')
        self.assertEqual(kwargs['params']['allow_long_transcription'],'false')
        self.assertEqual(kwargs['params']['cache_max_age'],'30d')
        self.assertEqual(kwargs['headers']['x-api-key'],'fixture-key')

    def test_never_automatically_calls_api_without_both_gates(self):
        with patch.dict('os.environ',{'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'1',
                                      'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'0',
                                      'REELBRAIN_TRANSCRIPT_API_KEY':'fixture'}):
            self.assertFalse(hosted_transcript_enabled())
        with patch.dict('os.environ',{'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'0',
                                      'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
                                      'REELBRAIN_TRANSCRIPT_API_KEY':'fixture'}):
            self.assertFalse(hosted_transcript_enabled())
        with patch.dict('os.environ',{'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'1',
                                      'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
                                      'REELBRAIN_TRANSCRIPT_API_KEY':'fixture'}):
            self.assertTrue(hosted_transcript_enabled())

    def test_rejects_malicious_forged_url_and_oversized_transcript(self):
        with self.assertRaises(Exception):
            normalize_transcript('http://127.0.0.1/reel/DgGHCjZIZtW/',
                    {'success':True,'transcripts':[]})
        with self.assertRaises(TranscriptProviderError):
            normalize_transcript('https://instagram.com/reel/DgGHCjZIZtW/',
                    {'success':True,'transcripts':[{'shortcode':'DgGHCjZIZtW','text':'x'*90000}]})


if __name__=='__main__':unittest.main()
