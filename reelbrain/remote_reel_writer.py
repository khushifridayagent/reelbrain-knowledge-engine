"""Persist verified-*source* Reel evidence from a local extraction into the new private Postgres DB.

Saves each source observation plus its locator and citations; never upgrades model
inference to independent verification. Transactional, idempotent writes.
"""
from __future__ import annotations
import json,re
from .store import KnowledgeStore
from .sources import canonicalize_instagram
from .media_evidence_summary import build_media_summary

class RemoteWriteError(RuntimeError):pass

def media_persistence_decision(observations,result):
    """Use the same completion gate for queue status and knowledge projection."""
    from .resumable_media import required_incomplete_stages
    incomplete=required_incomplete_stages(result)
    summary=build_media_summary(observations,result)
    if summary['processing_stage']!='completed':
        if not incomplete:incomplete=['completion_evidence']
        return 'partial',incomplete,summary
    return 'evidence_saved',incomplete,summary

def save_reel_to_postgres(local:KnowledgeStore,pg,url:str,result:dict)->dict:
    canonical=canonicalize_instagram(url)
    source_id=result.get('source_id')
    if not isinstance(source_id,str) or not source_id:raise RemoteWriteError('local result has no source receipt')
    media_sha=result.get('media_sha256')
    if not isinstance(media_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',media_sha):
        raise RemoteWriteError('real local media SHA256 is required for remote persistence')
    if not result.get('processing_receipt_id'):
        raise RemoteWriteError('actual media receipt required for remote persistence')
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
    status,incomplete,summary=media_persistence_decision([dict(ev) for ev in observations],result)
    with pg.transaction():
        with pg.cursor() as cur:
            cur.execute('''insert into reelbrain_research.reel_sources
                (canonical_url,local_source_id,status,media_sha256,completeness,stage_timings,stage_errors)
                values (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
                on conflict(canonical_url) do update set
                  status=CASE WHEN reelbrain_research.reel_sources.status='evidence_saved'
                       THEN 'evidence_saved' ELSE excluded.status END,
                  local_source_id=excluded.local_source_id,
                  media_sha256=CASE WHEN reelbrain_research.reel_sources.status='evidence_saved'
                       AND reelbrain_research.reel_sources.media_sha256 IS NOT NULL
                       THEN reelbrain_research.reel_sources.media_sha256
                       ELSE excluded.media_sha256 END,
                  completeness=excluded.completeness,stage_timings=excluded.stage_timings,
                  stage_errors=excluded.stage_errors,updated_at=now()''',
                (canonical,source_id,status,media_sha,result.get('knowledge_completeness','NOT_AUDITED'),
                 json.dumps(result.get('stage_timings_ms',{})),json.dumps(result.get('stage_errors',{}))))
            for ev in observations:
                cur.execute('''insert into reelbrain_research.reel_observations(source_url,observation_id,evidence_kind,locator,verbatim)
                    values(%s,%s,%s,%s,%s) on conflict(source_url,observation_id) do nothing''',
                    (canonical,ev['id'],ev['kind'],ev['locator'],ev['verbatim']))
            for r in resources:
                cur.execute('''insert into reelbrain_research.reel_resources(source_url,canonical_resource_url,resource_name,claimed_purpose,observation_id)
                   values(%s,%s,%s,%s,%s) on conflict do nothing''',
                   (canonical,r['canonical_url'],r['name'],r['purpose'],r['evidence_id']))
            # Project each real observation into the searchable evidence row without
            # changing the independently researched public metadata/caption.
            # Keep inference separate: a VLM's assertion is NOT verified video proof.
            source_trace={'kind':'authorized_media_processing',
                          'source_id':source_id,'provider':result.get('provider','unknown'),
                          'modality_audit':'NOT_AUDITED','external_claims_verified':False}
            cur.execute('''insert into public.reelbrain_reel_knowledge
                (source_url,source_provider,verified_reel_content,content_evidence,
                 video_analyzed,audio_transcribed,ocr_analyzed,processing_stage)
                values(%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)
                on conflict(source_url) do update set
                  verified_reel_content=public.reelbrain_reel_knowledge.verified_reel_content ||
                    excluded.verified_reel_content,
                  content_evidence=case
                    when public.reelbrain_reel_knowledge.content_evidence @> excluded.content_evidence
                    then public.reelbrain_reel_knowledge.content_evidence
                    else public.reelbrain_reel_knowledge.content_evidence || excluded.content_evidence end,
                  video_analyzed=public.reelbrain_reel_knowledge.video_analyzed or excluded.video_analyzed,
                  audio_transcribed=public.reelbrain_reel_knowledge.audio_transcribed or excluded.audio_transcribed,
                  ocr_analyzed=public.reelbrain_reel_knowledge.ocr_analyzed or excluded.ocr_analyzed,
                  processing_stage=excluded.processing_stage,
                  updated_at=now()''',
                (canonical,str(result.get('provider') or 'reelbrain-media-worker')[:100],
                 json.dumps(summary['content'],ensure_ascii=False),
                 json.dumps([source_trace],ensure_ascii=False),
                 summary['video_analyzed'],summary['audio_transcribed'],
                 summary['ocr_analyzed'],summary['processing_stage']))
    from .resumable_media import retry_seconds
    # Preserve successful OCR/ASR even when a remote model quota is exhausted.
    # Return a numeric retry hint only; never print provider error bodies.
    retry_after=(retry_seconds({stage:(result.get('stage_errors') or {}).get(stage,'required modality not attempted') for stage in incomplete}) or 3600
                 if status=='partial' else None)
    return {'source_url':canonical,'source_id':source_id,'observation_count':len(observations),
            'resource_citations':len(resources),'status':status,'persisted_in_postgres':True,
            'transient_model_retry_seconds':retry_after,
            'incomplete_stages':incomplete}
