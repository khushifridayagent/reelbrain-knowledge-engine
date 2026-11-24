"""Elastic Reel intake: quota-aware ASR must not hard-stop at 60/day."""
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from reelbrain.transcriptfetch_api import (
    TranscriptFetchClient,TranscriptFetchError,TranscriptFetchQuotaError,
    TranscriptFetchRateLimitError
)
from reelbrain.hosted_transcript_job import run_one_hosted_transcript,run_hosted_transcript_drain,_reserve_one

SOURCE='https://www.instagram.com/reel/DaQLc80PIBU/'


class Response:
    def __init__(self, body,status=200,headers=None):
        self.body,self.status_code,self.headers=body,status,headers or {}
    def raise_for_status(self):
        if self.status_code>=400:raise RuntimeError('remote http error')
    def json(self):return self.body


class HTTP:
    def __init__(self,resp):self.resp=resp;self.calls=[]
    def get(self,url,**kwargs):self.calls.append(('GET',url,kwargs));return self.resp
    def post(self,url,**kwargs):self.calls.append(('POST',url,kwargs));return self.resp


class DB:
    def __enter__(self):return self
    def __exit__(self,*args):return False


class FakeBalanceClient:
    def __init__(self,credits):self.credits=credits;self.starts=[]
    def balance(self):return self.credits
    def start(self,url):
        self.starts.append(url)
        return {'state':'completed','transcript':{
            'provider':'transcriptfetch','text':'A spoken transcript',
            'segments':[]}}
    def poll(self,url,jobid):raise AssertionError('Unexpected job poll')


class SQLCursor:
    def __init__(self):self.executed=[];self.index=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,params=None):self.executed.append((sql,params))
    def fetchone(self):
        self.index+=1
        if self.index==1:return (SOURCE,)
        return (1,)


class SQLDB:
    def __init__(self):self.cur=SQLCursor()
    def transaction(self):return nullcontext()
    def cursor(self):return self.cur


class ElasticTranscriptTests(unittest.TestCase):
    def test_free_balance_is_checked_without_spending_api_credits(self):
        h=HTTP(Response({'ok':True,'data':{'kind':'me','credits':17},'usage':{'balance':17}}))
        self.assertEqual(TranscriptFetchClient('fixture-key',http=h).balance(),17)
        self.assertEqual(h.calls[0][0],'GET')
        self.assertEqual(h.calls[0][1],'https://transcriptfetch.com/api/v2/me')
        self.assertEqual(h.calls[0][2]['headers']['Authorization'],'Bearer fixture-key')

    def test_zero_and_invalid_balance_fail_closed(self):
        for payload,expected in [
            ({'ok':True,'data':{'kind':'me','credits':0}},0),
            ({'ok':True,'data':{'kind':'me','credits':-2}},None),
            ({'ok':True,'data':{'kind':'me','credits':'100'}},None),
            ({'ok':False,'error':'secret should not leak'},None),
        ]:
            h=HTTP(Response(payload))
            c=TranscriptFetchClient('fixture',http=h)
            if expected is None:
                with self.assertRaises(TranscriptFetchError) as ctx:c.balance()
                self.assertNotIn('secret should not leak',str(ctx.exception))
            else:self.assertEqual(c.balance(),expected)

    def test_402_and_429_are_distinct_uncounted_provider_failures(self):
        h=HTTP(Response({'ok':False,'error':{'code':'insufficient_credits'}},402))
        with self.assertRaises(TranscriptFetchQuotaError):
            TranscriptFetchClient('fixture',http=h).start(SOURCE)
        h2=HTTP(Response({'ok':False,'error':{'code':'rate_limited'}},429,{'Retry-After':'15'}))
        with self.assertRaises(TranscriptFetchRateLimitError):
            TranscriptFetchClient('fixture',http=h2).start(SOURCE)

    def test_zero_balance_pauses_without_claiming_or_losing_any_source(self):
        env={'REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER':'transcriptfetch',
             'TRANSCRIPTFETCH_API_KEY':'fixture',
             'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'1',
             'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1'}
        with patch.dict('os.environ',env,clear=True), \
             patch('reelbrain.durable_worker.checked_config',return_value={'db_url':'fixture'}), \
             patch('reelbrain.hosted_transcript_job._poll_one',return_value=None), \
             patch('reelbrain.hosted_transcript_job._reserve_one') as claim:
            status=run_one_hosted_transcript(client=FakeBalanceClient(0),connection_factory=lambda _:DB())
            self.assertEqual(status['status'],'credits_exhausted_wait_for_refill')
            self.assertEqual(status['requests_sent'],0)
            claim.assert_not_called()

    def test_after_refill_the_same_pending_queue_resumes_without_var_change(self):
        env={'REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER':'transcriptfetch',
             'TRANSCRIPTFETCH_API_KEY':'fixture',
             'REELBRAIN_HOSTED_TRANSCRIPT_ENABLED':'1',
             'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
             'REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT':'60'}
        with patch.dict('os.environ',env,clear=True), \
             patch('reelbrain.durable_worker.checked_config',return_value={'db_url':'fixture'}), \
             patch('reelbrain.hosted_transcript_job._poll_one',return_value=None), \
             patch('reelbrain.hosted_transcript_job._reserve_one',return_value=SOURCE) as claim, \
             patch('reelbrain.hosted_transcript_job._finalize',return_value=True):
            for credits,expected in [(0,'credits_exhausted_wait_for_refill'),(17,'transcript_saved')]:
                client=FakeBalanceClient(credits)
                got=run_one_hosted_transcript(client=client,connection_factory=lambda _:DB())
                self.assertEqual(got['status'],expected)
            self.assertEqual(claim.call_count,1)

    def test_transcriptfetch_counts_daily_starts_for_auditing_not_a_sixty_reel_ceiling(self):
        with patch.dict('os.environ',{'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
                                       'REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT':'60'},clear=True):
            pg=SQLDB()
            self.assertEqual(_reserve_one(pg,'transcriptfetch'),SOURCE)
            sql=pg.cur.executed[2][0]
            self.assertIn('reserved_calls+1',sql)
            self.assertNotIn('reserved_calls < %s',sql)

    def test_bounded_run_chunks_continue_across_future_scheduled_ticks(self):
        responses=[
            {'status':'transcript_saved','requests_sent':1},
            {'status':'provider_async_processing','requests_sent':1},
            {'status':'transcript_saved','requests_sent':1},
            {'status':'queue_idle_or_legacy_daily_safety_cap','requests_sent':0},
        ]
        with patch('reelbrain.hosted_transcript_job.run_one_hosted_transcript',side_effect=responses) as fn:
            result=run_hosted_transcript_drain(max_jobs_per_tick=4,max_seconds=120)
        self.assertEqual(result['jobs_completed'],2)
        self.assertEqual(result['provider_starts'],3)
        self.assertEqual(fn.call_count,4)
        self.assertEqual(result['status'],'queue_idle')

    def test_backlog_tick_stops_as_soon_as_free_balance_is_empty(self):
        with patch('reelbrain.hosted_transcript_job.run_one_hosted_transcript',
                   return_value={'status':'credits_exhausted_wait_for_refill','requests_sent':0}) as fn:
            result=run_hosted_transcript_drain(max_jobs_per_tick=8,max_seconds=200)
        self.assertEqual(fn.call_count,1)
        self.assertEqual(result['status'],'credits_exhausted_wait_for_refill')

if __name__=='__main__':unittest.main()
