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


def _reserve_one(pg):
    """Reserve one provider call with transactional day cap and source lease.

    Advisory xact lock serializes claims across multiple runners. Requests are
    reserved *before* API work to fail closed on crashes and duplicate runs.
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
                   AND (a.source_url IS NULL OR (a.attempts < 3 AND a.next_attempt_at <= now()))
                 ORDER BY k.created_at,k.source_url LIMIT 1
            """)
            hit=cur.fetchone()
            if not hit:return None
            source_url=hit[0]
            cur.execute("""
                INSERT INTO reelbrain_research.hosted_transcript_daily_budget
                  (usage_day,reserved_calls) VALUES ((now() at time zone 'UTC')::date,1)
                ON CONFLICT (usage_day) DO UPDATE SET
                  reserved_calls=reelbrain_research.hosted_transcript_daily_budget.reserved_calls+1,
                  updated_at=now()
                WHERE reelbrain_research.hosted_transcript_daily_budget.reserved_calls < 2
                RETURNING reserved_calls
            """)
            if cur.fetchone() is None:
                return None
            cur.execute("""
                INSERT INTO reelbrain_research.hosted_transcript_attempts
                  (source_url,attempts,state,last_attempt_at,next_attempt_at)
                VALUES (%s,1,'claimed',now(),now()+interval '48 hours')
                ON CONFLICT (source_url) DO UPDATE SET
                  attempts=reelbrain_research.hosted_transcript_attempts.attempts+1,
                  state='claimed',
                  last_attempt_at=now(),
                  next_attempt_at=now()+interval '48 hours',
                  updated_at=now()
            """,(source_url,))
            return source_url


def _finalize(pg,url:str,transcript:dict|None,error_category:str|None=None)->bool:
    with pg.transaction():
        with pg.cursor() as cur:
            if transcript:
                # Transcript-only notes DO NOT mark first-party ASR/OCR complete.
                # Preserve any independently verified media and original caption.
                record={
                    'provider':'scrapecreators',
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
                          'provider','scrapecreators',
                          'is_first_party_media_evidence',false,
                          'visual_frames_analyzed',false,
                          'source_url',%s)),
                      updated_at=now()
                    WHERE source_url=%s AND NOT
                      (coalesce(verified_reel_content,'{}'::jsonb) ? 'provider_audio_transcript')
                    RETURNING source_url
                """,(json.dumps(record,ensure_ascii=False),url,url))
                saved=cur.fetchone() is not None
            else:saved=False
            state='completed' if saved else ('retry' if error_category else 'no_speech')
            cur.execute("""
                UPDATE reelbrain_research.hosted_transcript_attempts SET
                    state=%s,
                    last_category=%s,
                    next_attempt_at=CASE WHEN %s='completed' THEN now()+interval '365 days'
                         WHEN %s='no_speech' THEN now()+interval '90 days'
                         ELSE now()+interval '48 hours' END,
                    updated_at=now()
                WHERE source_url=%s
            """,(state,error_category,state,state,url))
    return saved


def run_one_hosted_transcript(db_url:str|None=None,*,client=None,connection_factory=None)->dict:
    """Optional single-request, bounded-budget stage.

    Does not consume the media worker queue lease and cannot suppress later
    OCR, video understanding or original-media retry attempts.
    """
    if not hosted_transcript_enabled():
        return {'status':'disabled','requests_sent':0}
    db_url=db_url or os.environ.get('REELBRAIN_DB_URL','')
    if not db_url:
        return {'status':'missing_database','requests_sent':0}
    if connection_factory is None:
        from .durable_worker import pg_open
        connection_factory=pg_open
    with connection_factory(db_url) as pg:
        url=_reserve_one(pg)
        if not url:
            return {'status':'no_eligible_source_or_daily_budget','requests_sent':0}
        adapter=client or HostedTranscriptClient(os.environ['REELBRAIN_TRANSCRIPT_API_KEY'])
        try:
            transcript=adapter.fetch(url)
        except TranscriptProviderError as exc:
            _finalize(pg,url,None,error_category=type(exc).__name__)
            return {'status':'provider_failed_deferred','requests_sent':1}
        except Exception as exc:
            _finalize(pg,url,None,error_category=type(exc).__name__[:60])
            return {'status':'provider_failed_deferred','requests_sent':1}
        persisted=_finalize(pg,url,transcript)
        return {'status':'transcript_saved' if persisted else 'no_speech_or_duplicate',
                'requests_sent':1}
