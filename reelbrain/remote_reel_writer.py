"""Persist verified-*source* Reel evidence from a local extraction into the new private Postgres DB.

Saves each source observation plus its locator and citations; never upgrades model
inference to independent verification. Transactional, idempotent writes.
"""
from __future__ import annotations
import json
from .store import KnowledgeStore
from .sources import canonicalize_instagram

class RemoteWriteError(RuntimeError):pass

def save_reel_to_postgres(local:KnowledgeStore,pg,url:str,result:dict)->dict:
    canonical=canonicalize_instagram(url)
    source_id=result.get('source_id')
    if not isinstance(source_id,str) or not source_id:raise RemoteWriteError('local result has no source receipt')
    source=local.con.execute('SELECT id FROM sources WHERE id=? AND tenant=?',(source_id,result.get('tenant','personal'))).fetchone()
    if source is None:
        # Older engine results do not have tenant field; reference by globally unique source ID.
        source=local.con.execute('SELECT id FROM sources WHERE id=?',(source_id,)).fetchone()
    if source is None:raise RemoteWriteError('result refers to non-existent local source')
    observations=local.con.execute('SELECT id,kind,locator,verbatim FROM evidence WHERE source_id=?',(source_id,)).fetchall()
    resources=local.con.execute('''SELECT r.canonical_url,r.name,r.purpose,c.evidence_id
       FROM citations c join resources r on r.id=c.resource_id and r.tenant=c.tenant
       where c.source_id=?''',(source_id,)).fetchall()
    valid_obs={x['id'] for x in observations}
    if any(r['evidence_id'] not in valid_obs for r in resources):raise RemoteWriteError('citation references evidence outside the source')
    if not observations:raise RemoteWriteError('no real source observations to persist')
    # Absence of audio/visual/verification: partial is an honest receipt, not a fully understood Reel.
    status='partial' if result.get('status')=='partial' or result.get('unattempted_modalities') else 'evidence_saved'
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute('''insert into reelbrain_research.reel_sources
                (canonical_url,local_source_id,status,media_sha256,completeness,stage_timings,stage_errors)
                values (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                on conflict(canonical_url) do update set
                  status=excluded.status,local_source_id=excluded.local_source_id,
                  completeness=excluded.completeness,stage_timings=excluded.stage_timings,
                  stage_errors=excluded.stage_errors,updated_at=now()''',
                (canonical,source_id,status,None,result.get('knowledge_completeness','NOT_AUDITED'),
                 json.dumps(result.get('stage_timings_ms',{})),json.dumps(result.get('stage_errors',{}))))
            for ev in observations:
                cur.execute('''insert into reelbrain_research.reel_observations(source_url,observation_id,evidence_kind,locator,verbatim)
                    values(%s,%s,%s,%s,%s) on conflict(source_url,observation_id) do nothing''',
                    (canonical,ev['id'],ev['kind'],ev['locator'],ev['verbatim']))
            for r in resources:
                cur.execute('''insert into reelbrain_research.reel_resources(source_url,canonical_resource_url,resource_name,claimed_purpose,observation_id)
                   values(%s,%s,%s,%s,%s) on conflict do nothing''',
                   (canonical,r['canonical_url'],r['name'],r['purpose'],r['evidence_id']))
    return {'source_url':canonical,'source_id':source_id,'observation_count':len(observations),
            'resource_citations':len(resources),'status':status,'persisted_in_postgres':True}
