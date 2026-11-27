"""Admission control for already-deferred work during shared model outages.

This is an optimization, not evidence or a replacement for provider-level
cooldowns. The existing lease/attempt invariants remain unchanged.
"""
from __future__ import annotations
import os

QUOTA_WAIT_FILTER = """not (status='queued' and
    coalesce(last_error,'')='Model quota temporarily unavailable')"""


def configured_vision_keys():
    """Match the worker's explicitly enabled native hybrid providers."""
    if os.getenv('REELBRAIN_NATIVE_HYBRID_ENABLED','').lower() not in ('1','true','yes'):
        return ()
    if os.getenv('REELBRAIN_MEDIA_ACQUISITION','yt_dlp_public').strip().lower()!='yt_dlp_public':
        return ()
    from .cloudflare_vision_config import cloudflare_qwen_config
    keys=[]
    if os.getenv('GEMINI_API_KEY'):keys.append('gemini_vision')
    if os.getenv('GROQ_API_KEY'):keys.append('groq_vision')
    if cloudflare_qwen_config():keys.append('cloudflare_vision')
    return tuple(keys)


def all_vision_blocked_seconds(cur,keys):
    """Missing/expired provider entries mean admission remains open."""
    if not keys:return 0
    cur.execute("""select provider,greatest(0,ceil(extract(epoch from
        blocked_until-now())))::int
        from reelbrain_research.hybrid_provider_cooldowns
        where provider=any(%s)""",(list(keys),))
    delays=dict(cur.fetchall())
    if any(delays.get(key,0)<=0 for key in keys):return 0
    return min(delays[key] for key in keys)


def claim_media_jobs(cur,batch_size,blocked_seconds):
    count=min(10,max(1,batch_size))
    if not blocked_seconds:
        cur.execute('select id,source_url,lease_token from public.reelbrain_claim_dm_jobs(%s,%s)',
                    (count,900))
        return
    # Same atomic FIFO claim as the existing RPC, with one additional
    # predicate. Never update availability, reset attempts or touch active
    # leases. A different worker may observe a provider refill immediately.
    cur.execute("""with selected as (
        select id from public.reelbrain_dm_jobs
        where ((status='queued' and available_at<=now())
            or (status='leased' and lease_until<now()))
          and attempts<max_attempts and """+QUOTA_WAIT_FILTER+"""
        order by available_at,id for update skip locked limit %s
    )
    update public.reelbrain_dm_jobs j
      set status='leased',lease_token=gen_random_uuid(),
          lease_until=now()+interval '900 seconds',
          attempts=j.attempts+1,updated_at=now()
    from selected where j.id=selected.id
    returning j.id,j.source_url,j.lease_token""",(count,))
