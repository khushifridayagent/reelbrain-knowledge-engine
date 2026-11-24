"""Three ordered stages per Reel, bounded overlap across Reels.
One acquisition, one analysis and one persistence slot per runner.
No raw media leaves the runner for checkpoint storage.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from threading import Semaphore, local
from contextlib import contextmanager
import time

# Legacy rows from older workers may be stranded in terminal states after
# provider outages. Never re-open processed jobs or arbitrary software bugs.
RECOVERABLE_TERMINAL_SQL = """(status='partial' OR
    (status='dead_letter' AND
     (lower(coalesce(last_error,'')) LIKE 'metamediaunavailable: public media unavailable:%'
      OR lower(coalesce(last_error,'')) LIKE 'publicbundleerror: public media unavailable:%'
      OR lower(coalesce(last_error,'')) LIKE 'publicmediaerror: public media unavailable:%')
     AND (lower(coalesce(last_error,'')) LIKE '%token_expired_or_invalid%'
      OR lower(coalesce(last_error,'')) LIKE '%rate_limited%'
      OR lower(coalesce(last_error,'')) LIKE '%http_forbidden%'
      OR lower(coalesce(last_error,'')) LIKE '%login_required%'
      OR lower(coalesce(last_error,'')) LIKE '%credential_invalid%'
      OR lower(coalesce(last_error,'')) LIKE '%credits_exhausted%')))"""

_context=local()

@contextmanager
def stage_slot(stage):
    slots=getattr(_context,'slots',None)
    if slots is None:
        yield
    else:
        with slots[stage]:
            yield

def classify_model_http(code):
    if code in (402,429):return 'quota exceeded'
    if code in (502,503,504):return 'service unavailable'
    return f'visual request rejected HTTP {int(code)}'

def required_incomplete_stages(result):
    """Required media passes, not optional structured enrichment."""
    missing=set(result.get('stage_errors') or {})
    for stage in result.get('unattempted_modalities') or []:
        if stage=='video_model':
            missing.add(stage)
        elif stage=='asr' and result.get('audio_required',True) and not result.get('hosted_audio_reused'):
            missing.add(stage)
    return sorted(missing)

def retry_seconds(errors):
    from .model_quota_retry import model_quota_retry_seconds
    if not errors:return None
    return model_quota_retry_seconds(errors) or 3600

def drain_overlapping(config,*,max_jobs=4,process_batch=None,time_remaining=None):
    if not 1<=max_jobs<=10:raise ValueError('invalid batch size')
    if process_batch is None:
        from .durable_worker import run_one_batch
        process_batch=run_one_batch
    if time_remaining is None:
        end=time.monotonic()+3000
        time_remaining=lambda:end-time.monotonic()
    slots={stage:Semaphore(1) for stage in ('download','analysis','storage')}
    def work():
        _context.slots=slots
        try:return process_batch(config,batch_size=1)
        finally:del _context.slots
    outcomes=[]
    started=0
    exhausted=False
    with ThreadPoolExecutor(max_workers=3) as pool:
        pending=set()
        def fill():
            nonlocal started
            while not exhausted and len(pending)<3 and started<max_jobs and time_remaining()>=900:
                pending.add(pool.submit(work))
                started+=1
        fill()
        while pending:
            finished,pending=wait(pending,return_when=FIRST_COMPLETED)
            for f in finished:
                batch=f.result()
                if not isinstance(batch,list):raise RuntimeError('Invalid worker response')
                if not batch:exhausted=True
                for item in batch:
                    if item.get('status') in ('deferred_access','deferred_model_quota','retry_or_dead_letter') and not item.get('acknowledged_failure'):
                        raise RuntimeError('Unacknowledged durable failure')
                outcomes.extend(batch)
            fill()
    return outcomes
