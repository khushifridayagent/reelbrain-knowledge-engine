"""Independent, read-only health audit of durable queue progress."""
from __future__ import annotations

_FIELDS=("pending","old_pending","recent_completed","stale_leases","dead_letters")
def evaluate_health(row):
    if not isinstance(row,dict) or any(type(row.get(k)) is not int or row[k]<0 for k in _FIELDS):
        raise ValueError("Invalid queue health metrics")
    if row["old_pending"]>row["pending"]:
        raise ValueError("Inconsistent queue health metrics")
    alerts=[]
    if row["old_pending"] and not row["recent_completed"]:
        alerts.append("completion_stalled")
    if row["stale_leases"]:
        alerts.append("stale_lease")
    if row["dead_letters"]:
        alerts.append("dead_letter")
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
                 count(*) filter(where status='dead_letter')
          from public.reelbrain_dm_jobs
        """)
        row=dict(zip(_FIELDS,cur.fetchone(),strict=True))
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
