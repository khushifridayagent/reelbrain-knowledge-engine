"""Classify temporary quota/rate outages without misclassifying content errors.

Partial real-media evidence is persisted, but a model 429/402 must NOT
permanently finish the source. Re-attempt from its original URL only when
the durable lease's availability timer expires. All provider errors untrusted.
"""
from __future__ import annotations
from datetime import datetime,timedelta,timezone


def model_quota_retry_seconds(stage_errors:dict|None, *, now:datetime|None=None)->int|None:
    if not isinstance(stage_errors,dict):return None
    for stage in ('vlm','asr'):
        error=stage_errors.get(stage)
        if not isinstance(error,str):continue
        line=error.lower()[:250]
        if any(token in line for token in (
            'quota exceeded','insufficient credits','resource exhausted',
            '429','rate limit','rate_limit','neuron','402')):
            # Free Cloudflare model Neurons replenish daily; a conservative
            # check later avoids burning remaining quotas in a retry storm.
            if any(s in line for s in ('neuron','quota','resource exhausted')):
                current=now or datetime.now(timezone.utc)
                if current.tzinfo is None:raise ValueError('UTC-aware retry clock required')
                current=current.astimezone(timezone.utc)
                tomorrow=(current+timedelta(days=1)).date()
                next_refill=datetime.combine(tomorrow,datetime.min.time(),tzinfo=timezone.utc)
                # Five minutes after UTC midnight; database deferral uses
                # 15-minute minimum to prevent thundering-herd retries.
                next_refill+=timedelta(minutes=5)
                return max(900,min(86400,int((next_refill-current).total_seconds())))
            return 3600
        if any(s in line for s in ('503','502','service unavailable','upstream timed out')):
            return 3600
    return None
