"""Bounded overlapping jobs, each owning its own database connection."""
from concurrent.futures import ThreadPoolExecutor
import time

def storage_allowed(size):
    return 0 <= size < 280_000_000

def classify_model_http(code):
    if code in (402,429):return 'quota exceeded'
    if code in (502,503,504):return 'service unavailable'
    return f'visual request rejected HTTP {int(code)}'

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
    outcomes=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i in range(0,max_jobs,2):
            if time_remaining()<900:break
            futures=[pool.submit(process_batch,config,batch_size=1) for _ in range(min(2,max_jobs-i))]
            results=[f.result() for f in futures]
            for batch in results:
                for item in batch:
                    if item.get('status') in ('deferred_access','deferred_model_quota','retry_or_dead_letter') and not item.get('acknowledged_failure'):
                        raise RuntimeError('Unacknowledged durable failure')
                outcomes.extend(batch)
            if not any(results):break
    return outcomes
