"""Independent, read-only health audit of durable queue progress."""
from __future__ import annotations

_FIELDS=("pending","old_pending","recent_completed","stale_leases","dead_letters")
_EXTRA_ALERTS={
    "exhausted_queued":"exhausted_queued",
    "invalid_leases":"invalid_lease",
    "missing_availability":"missing_availability",
    "processed_without_completion":"completion_mismatch",
    "unresolved_incomplete":"unresolved_required_stage",
    "overdue_untouched":"queue_starvation",
}
_ALL_FIELDS=_FIELDS+tuple(_EXTRA_ALERTS)
def evaluate_health(row):
    if not isinstance(row,dict) or any(type(row.get(k)) is not int or row[k]<0 for k in _FIELDS):
        raise ValueError("Invalid queue health metrics")
    if any(type(row[k]) is not int or row[k]<0
           for k in _EXTRA_ALERTS if k in row):
        raise ValueError("Invalid additional queue health metrics")
    if row["old_pending"]>row["pending"]:
        raise ValueError("Inconsistent queue health metrics")
    alerts=[]
    if row["old_pending"] and not row["recent_completed"]:
        alerts.append("completion_stalled")
    if row["stale_leases"]:
        alerts.append("stale_lease")
    if row["dead_letters"]:
        alerts.append("dead_letter")
    alerts.extend(alert for metric,alert in _EXTRA_ALERTS.items() if row.get(metric,0))
    return alerts

def audit_queue(pg):
    with pg.cursor() as cur:
        cur.execute("""
          select count(*) filter(where status in ('queued','leased')),
                 count(*) filter(where status in ('queued','leased')
                                  and created_at<now()-interval '24 hours'),
                 count(*) filter(where status='processed'
                                  and updated_at>=now()-interval '24 hours'),
                 count(*) filter(where status='leased'
                                  and lease_until<now()-interval '30 minutes'),
                 count(*) filter(where status='dead_letter'),
                 count(*) filter(where status='queued' and attempts>=max_attempts),
                 count(*) filter(where status='leased' and (lease_token is null or lease_until is null)),
                 count(*) filter(where status='queued' and available_at is null),
                 count(*) filter(where status='processed' and not exists (
                   select 1 from public.reelbrain_reel_knowledge k
                   where k.source_url=j.source_url and k.processing_stage='completed')),
                 count(*) filter(where status='queued'
                   and last_error='Required media stage incomplete; automatic retry'
                   and created_at<now()-interval '24 hours'),
                 count(*) filter(where status='queued'
                   and available_at<now()-interval '48 hours'
                   and updated_at<now()-interval '48 hours')
          from public.reelbrain_dm_jobs j
        """)
        row=dict(zip(_ALL_FIELDS,cur.fetchone(),strict=True))
    return row,evaluate_health(row)

def main():
    import os
    from urllib.parse import urlsplit
    import psycopg
    db=os.environ.get('REELBRAIN_DB_URL','')
    try:
        p=urlsplit(db)
        ref='xlkdzrhzizuftbnitodr'
        if p.scheme not in ('postgres','postgresql') or ref not in (p.username or '').lower() and ref not in (p.hostname or '').lower():
            raise ValueError("Incorrect database")
        with psycopg.connect(db,connect_timeout=8,options='-c default_transaction_read_only=on -c statement_timeout=15000') as pg:
            row,alerts=audit_queue(pg)
    except Exception as exc:
        raise SystemExit('Queue health unavailable: '+type(exc).__name__) from None
    summary=['## Durable queue health (read-only)']+[f'- {key}: {value}' for key,value in row.items()]
    summary.append('Alerts: '+(', '.join(alerts) if alerts else 'none'))
    print('\n'.join(summary))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write('\n'.join(summary)+'\n')
    if alerts:
        raise SystemExit('Durable queue requires review: '+', '.join(alerts))

if __name__=='__main__':main()
