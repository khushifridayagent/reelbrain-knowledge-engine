"""A credit-capped, URL-first speech stage independent of video downloading.

Uses the same private PostgreSQL database; processing a third-party transcript
does NOT finish the Reel media job or claim that any frames were reviewed.
This module has NO side effects when owner approval/token is missing.
"""
from __future__ import annotations

import json
import os
from .hosted_transcript import (
    HostedTranscriptClient, TranscriptProviderError, hosted_transcript_enabled,
)
from .transcriptfetch_api import (
    TranscriptFetchClient,TranscriptFetchQuotaError,
    TranscriptFetchRateLimitError,TranscriptFetchAuthError,
)


def daily_transcript_request_cap()->int:
    """Maximum new hosted ASR billable STARTS per UTC day.

    Defaults to two; user may explicitly allow more after confirming the
    provider's current plan, purchase cap and genuine account credits.
    This is a request limit, not a monetary spend guarantee: long videos
    can cost multiple credits per start.
    """
    approved=os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED')=='1'
    value=os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT','2') if approved else '2'
    try:
        cap=int(value)
    except (TypeError,ValueError):
        raise ValueError('Hosted daily request limit must be an integer') from None
    if not 1<=cap<=120:
        raise ValueError('Hosted daily request limit must be between 1 and 120')
    return cap


def _reserve_one(pg,provider='scrapecreators'):
    """Reserve a fresh provider request under a global transaction lock.

    The daily cap is shared across all paid hosted transcript providers.
    Never start a second billable request for an outstanding 202 job.
    """
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('reelbrain_hosted_transcript_v1'))")
            cur.execute("""
                SELECT k.source_url
                  FROM public.reelbrain_reel_knowledge k
                  JOIN public.reelbrain_dm_jobs j ON j.source_url=k.source_url
                  LEFT JOIN reelbrain_research.hosted_transcript_attempts a
                    ON a.source_url=k.source_url
                 WHERE k.processing_stage='media_pending'
                   AND j.status IN ('queued','partial')
                   AND NOT (coalesce(k.verified_reel_content,'{}'::jsonb) ? 'provider_audio_transcript')
                   AND (a.source_url IS NULL
                        OR (a.state IN ('pending','retry')
                            AND a.next_attempt_at <= now())
                        OR (a.state='claimed'
                            AND a.last_attempt_at < now()-interval '60 minutes'))
                 ORDER BY j.created_at,j.id LIMIT 1
            """)
            hit=cur.fetchone()
            if not hit:return None
            url=hit[0]
            if provider=='transcriptfetch':
                # Enforce actual LIVE account credits (free GET /api/v2/me)
                # before claiming. This is a usage ledger, not a 60/day cap.
                cur.execute("""
                    INSERT INTO reelbrain_research.hosted_transcript_daily_budget
                      (usage_day,reserved_calls)
                    VALUES ((now() at time zone 'UTC')::date,1)
                    ON CONFLICT (usage_day) DO UPDATE SET
                      reserved_calls=reelbrain_research.hosted_transcript_daily_budget.reserved_calls+1,
                      updated_at=now()
                    RETURNING reserved_calls
                """)
            else:
                # Legacy ScrapeCreators mode still requires owner-approved
                # bounded starts because it lacks a verified live balance API.
                cur.execute("""
                    INSERT INTO reelbrain_research.hosted_transcript_daily_budget
                      (usage_day,reserved_calls)
                    VALUES ((now() at time zone 'UTC')::date,1)
                    ON CONFLICT (usage_day) DO UPDATE SET
                      reserved_calls=reelbrain_research.hosted_transcript_daily_budget.reserved_calls+1,
                      updated_at=now()
                    WHERE reelbrain_research.hosted_transcript_daily_budget.reserved_calls < %s
                    RETURNING reserved_calls
                """,(daily_transcript_request_cap(),))
            if cur.fetchone() is None:return None
            cur.execute("""
                INSERT INTO reelbrain_research.hosted_transcript_attempts
                  (source_url,attempts,state,provider,last_attempt_at,next_attempt_at)
                VALUES (%s,1,'claimed',%s,now(),now()+interval '48 hours')
                ON CONFLICT (source_url) DO UPDATE SET
                  attempts=least(3,reelbrain_research.hosted_transcript_attempts.attempts+1),
                  state='claimed',provider=excluded.provider,
                  provider_job_id=NULL,
                  last_attempt_at=now(),
                  next_attempt_at=now()+interval '48 hours',
                  updated_at=now()
            """,(url,provider))
            return url


def _poll_one(pg):
    """Poll outstanding TranscriptFetch 202 jobs without another paid start."""
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('reelbrain_hosted_transcript_v1'))")
            cur.execute("""
              SELECT source_url,provider_job_id
              FROM reelbrain_research.hosted_transcript_attempts
              WHERE provider='transcriptfetch' AND state='processing'
                AND next_attempt_at<=now() AND provider_job_id IS NOT NULL
              ORDER BY next_attempt_at,source_url LIMIT 1
            """)
            row=cur.fetchone()
            if not row:return None
            cur.execute("""
              UPDATE reelbrain_research.hosted_transcript_attempts
              SET next_attempt_at=now()+interval '15 minutes',
                  last_poll_at=now(),updated_at=now()
              WHERE source_url=%s AND state='processing'
            """,(row[0],))
            return row


def _mark_processing(pg,url,job_id,category=None):
    from .transcriptfetch_api import validate_poll_id
    job_id=validate_poll_id(job_id)
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute("""
              UPDATE reelbrain_research.hosted_transcript_attempts
              SET state='processing',provider='transcriptfetch',
                  provider_job_id=%s,last_category=%s,
                  next_attempt_at=now()+interval '5 minutes',
                  updated_at=now()
              WHERE source_url=%s
            """,(job_id,category,url))


def _finalize(pg,url:str,transcript:dict|None,error_category:str|None=None)->bool:
    with pg.transaction():
        with pg.cursor() as cur:
            if transcript:
                # Transcript-only notes DO NOT mark first-party ASR/OCR complete.
                # Preserve any independently verified media and original caption.
                provider=transcript.get('provider')
                if provider not in ('scrapecreators','transcriptfetch'):
                    raise RuntimeError('Unrecognized hosted speech provider')
                record={
                    'provider':provider,
                    'source_type':'third_party_asr_by_reel_url',
                    'text':transcript['text'],
                    'segments':transcript['segments'],
                    'source_media_directly_verified':False,
                    'visual_frames_verified':False,
                    'summary_language':'English',
                }
                cur.execute("""
                    UPDATE public.reelbrain_reel_knowledge SET
                      verified_reel_content=coalesce(verified_reel_content,'{}'::jsonb) ||
                        jsonb_build_object('provider_audio_transcript',%s::jsonb),
                      content_evidence=coalesce(content_evidence,'[]'::jsonb) ||
                        jsonb_build_array(jsonb_build_object(
                          'kind','third_party_url_audio_transcription',
                          'provider',%s::text,
                          'is_first_party_media_evidence',false,
                          'visual_frames_analyzed',false,
                          'source_url',%s::text)),
                      updated_at=now()
                    WHERE source_url=%s AND NOT
                      (coalesce(verified_reel_content,'{}'::jsonb) ? 'provider_audio_transcript')
                    RETURNING source_url
                """,(json.dumps(record,ensure_ascii=False),provider,url,url))
                saved=cur.fetchone() is not None
            else:saved=False
            state='completed' if saved else ('retry' if error_category else 'no_speech')
            cur.execute("""
                UPDATE reelbrain_research.hosted_transcript_attempts SET
                    state=%s,
                    last_category=%s,
                    next_attempt_at=CASE WHEN %s='completed' THEN now()+interval '365 days'
                         WHEN %s='no_speech' THEN now()+interval '90 days'
                         WHEN reelbrain_research.hosted_transcript_attempts.attempts>=3
                              THEN now()+interval '7 days'
                         ELSE now()+interval '48 hours' END,
                    updated_at=now()
                WHERE source_url=%s
            """,(state,error_category,state,state,url))
    return saved


def _defer_unbilled(pg,url,category:str,seconds:int=1800)->None:
    """402/429 never exhaust a Reel's limited source-failure retries."""
    if not 60<=seconds<=86400:
        raise ValueError('Invalid provider retry delay')
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute("""
                UPDATE reelbrain_research.hosted_transcript_attempts SET
                  state='retry',attempts=greatest(0,attempts-1),
                  provider_job_id=NULL,last_category=%s,
                  next_attempt_at=now()+make_interval(secs=>%s),
                  updated_at=now()
                WHERE source_url=%s
            """,(category[:60],seconds,url))


def run_one_hosted_transcript(db_url:str|None=None,*,client=None,connection_factory=None)->dict:
    """Process ONE due ASR task; pause on actual zero balance, never discard work.

    Existing Supabase queue is the unlimited intake buffer. No arbitrary
    daily incoming-Reel cap: TranscriptFetch's LIVE balance is authoritative,
    and an empty account resumes automatically when balance becomes positive.
    Credit-check and async polling are free provider operations.
    """
    if not hosted_transcript_enabled():
        return {'status':'disabled','requests_sent':0}
    from .durable_worker import checked_config
    validated=checked_config()['db_url']
    if db_url is not None and db_url!=validated:
        raise RuntimeError('Transcript worker must use isolated Reelbrain database')
    if connection_factory is None:
        from .durable_worker import pg_open
        connection_factory=pg_open
    provider=os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER','scrapecreators').strip().lower()
    if provider not in ('scrapecreators','transcriptfetch'):
        raise RuntimeError('Invalid hosted transcript provider')
    if provider=='transcriptfetch':
        adapter=client or TranscriptFetchClient(os.environ['TRANSCRIPTFETCH_API_KEY'])
    else:
        adapter=client or HostedTranscriptClient(os.environ['REELBRAIN_TRANSCRIPT_API_KEY'])
    with connection_factory(validated) as pg:
        pending=_poll_one(pg) if provider=='transcriptfetch' else None
        if pending:
            url,job_id=pending
            try:
                response=adapter.poll(url,job_id)
            except TranscriptFetchQuotaError:
                _defer_unbilled(pg,url,'insufficient_credits',seconds=1800)
                return {'status':'credits_exhausted_wait_for_refill','requests_sent':0}
            except Exception as exc:
                _mark_processing(pg,url,job_id,error_category_for(exc))
                return {'status':'poll_retry','requests_sent':0}
            if response['state']=='processing':
                _mark_processing(pg,url,job_id)
                return {'status':'still_processing','requests_sent':0}
            persisted=_finalize(pg,url,response.get('transcript'))
            return {'status':'transcript_saved' if persisted else 'no_speech_or_duplicate',
                    'requests_sent':0}

        if provider=='transcriptfetch':
            # Check credits BEFORE claim; free, supports both one-off balances
            # and actually recurring monthly refills without human resets.
            try:
                credits=adapter.balance()
            except TranscriptFetchAuthError:
                return {'status':'credential_invalid','requests_sent':0}
            except Exception:
                return {'status':'account_balance_unavailable','requests_sent':0}
            if credits<1:
                return {'status':'credits_exhausted_wait_for_refill','requests_sent':0}

        url=_reserve_one(pg,provider)
        if not url:return {'status':'queue_idle_or_legacy_daily_safety_cap','requests_sent':0}
        try:
            response=adapter.start(url) if provider=='transcriptfetch' else {
                'state':'completed','transcript':adapter.fetch(url)}
            if response['state']=='processing':
                _mark_processing(pg,url,response['job_id'])
                return {'status':'provider_async_processing','requests_sent':1}
            transcript=response.get('transcript')
        except TranscriptFetchQuotaError:
            _defer_unbilled(pg,url,'insufficient_credits',seconds=1800)
            return {'status':'credits_exhausted_wait_for_refill','requests_sent':1}
        except TranscriptFetchRateLimitError:
            _defer_unbilled(pg,url,'rate_limited',seconds=900)
            return {'status':'provider_rate_limited','requests_sent':1}
        except TranscriptFetchAuthError:
            _defer_unbilled(pg,url,'credential_invalid',seconds=7200)
            return {'status':'credential_invalid','requests_sent':1}
        except Exception as exc:
            _finalize(pg,url,None,error_category=error_category_for(exc))
            return {'status':'provider_failed_deferred','requests_sent':1}
        persisted=_finalize(pg,url,transcript)
        return {'status':'transcript_saved' if persisted else 'no_speech_or_duplicate',
                'requests_sent':1}


def run_hosted_transcript_drain(*,max_jobs_per_tick:int=2,max_seconds:int=100)->dict:
    """Bound per-GitHub-run work, NOT daily input count.

    Every future 5-minute tick resumes any remaining rows; 0/100/200 incoming
    Reels are all retained in the same durable DB queue.
    """
    import time
    if not 1<=max_jobs_per_tick<=8:
        raise ValueError('Per-run worker batch outside safe GitHub timeout')
    if not 10<=max_seconds<=240:
        raise ValueError('Per-run transcript window outside safe runner timeout')
    start=time.monotonic()
    results=[]
    terminal={'disabled','credits_exhausted_wait_for_refill',
              'provider_rate_limited','account_balance_unavailable',
              'credential_invalid','queue_idle_or_legacy_daily_safety_cap'}
    while len(results)<max_jobs_per_tick and (time.monotonic()-start)<max_seconds:
        status=run_one_hosted_transcript()
        results.append(status)
        if status['status'] in terminal:break
    return {
        'status':('queue_idle' if results and
                  results[-1]['status']=='queue_idle_or_legacy_daily_safety_cap'
                  else results[-1]['status'] if results else 'runner_window_elapsed'),
        'jobs_completed':sum(int(v['status']=='transcript_saved') for v in results),
        'provider_starts':sum(int(v['requests_sent']) for v in results),
        'tasks_touched':len(results)
    }


def error_category_for(exc:Exception)->str:
    # No raw provider error body, token, or Reel URL in persistent ledger.
    return type(exc).__name__[:60]
