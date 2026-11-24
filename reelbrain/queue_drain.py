"""Bounded automatic queue drain for short-lived GitHub Actions runners.

A Reel message is durably enqueued by Supabase; this runner polls and drains
eligible work without a per-video Git commit, long-lived host or raw media
storage. Reentrant queue claims are guarded by Postgres lease functions.
"""
from __future__ import annotations
import time
from typing import Callable


def drain_ready_queue(
    config: dict | None = None, *,
    max_jobs: int = 4,
    time_remaining: Callable[[], float] | None = None,
    process_batch: Callable | None = None,
) -> list[dict]:
    """Claim at most max_jobs in series while enough runner time remains.

    A failed public acquisition is put on server-side backoff. Other eligible
    jobs should still be tried in the same run. But a failed queue ACK is
    fatal: don't continue claiming jobs if durable ownership is uncertain.
    """
    if not isinstance(max_jobs,int) or not 1 <= max_jobs <= 10:
        raise ValueError('max_jobs must be between 1 and 10')
    if config is None or process_batch is None:
        from .durable_worker import checked_config, run_one_batch
        if config is None:
            config=checked_config()
        if process_batch is None:
            process_batch=run_one_batch
    if time_remaining is None:
        stop_at=time.monotonic()+660
        time_remaining=lambda: stop_at-time.monotonic()

    outcomes=[]
    for _ in range(max_jobs):
        # Allow up to 3 minutes for the next acquire/decode attempt. Any job
        # exceeding runtime limits is recovered later by the DB lease reaper.
        if time_remaining()<180:
            break
        result=process_batch(config,batch_size=1)
        if not isinstance(result,list):
            raise RuntimeError('Worker batch response is invalid')
        for item in result:
            if not isinstance(item,dict):
                raise RuntimeError('Worker returned malformed job result')
            if item.get('status') in ('deferred_access','deferred_model_quota','retry_or_dead_letter') and not item.get('acknowledged_failure'):
                raise RuntimeError('Durable job failure was not acknowledged')
        outcomes.extend(result)
        if not result:
            break
    return outcomes
