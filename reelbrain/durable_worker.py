"""Optional external media worker; no paid calls without all explicit gates.

The webhook persists URLs and returns immediately. This worker is a separate
process and must run on authorized compute for unattended jobs.

RUN only after configuring the dedicated REELBRAIN_DB_URL and user-approved
public media research flags. Apify is optional and explicitly paid-only.
Never reuse other projects.
"""
from __future__ import annotations
import json,os,time
from pathlib import Path
from urllib.parse import urlsplit
from contextlib import contextmanager
from .resumable_media import stage_slot
from .store import KnowledgeStore
from .remote_reel_writer import save_reel_to_postgres
from .link_processor import process_instagram_link, LinkProcessingOptions
from .acquire_apify import ApifyReelClient,SafeMediaDownloader
from .engine import LocalPipelineEngine
from .providers import GroqSpeechToText, GeminiVideoResearcher,ProviderOptions

def flag(k:str)->bool:return os.getenv(k,'').lower() in ('true','yes','1')
def checked_config()->dict:
    """Fail closed before claiming any queued job, with no surprise paid calls."""
    missing=[]
    db_url=os.getenv('REELBRAIN_DB_URL','')
    if not db_url:
        missing.append('REELBRAIN_DB_URL')
    else:
        # Enforce that GitHub never claims work from any unrelated Supabase
        # project even if the owner accidentally saved the wrong URI.
        try:
            uri=urlsplit(db_url)
            project_ref='xlkdzrhzizuftbnitodr'
            valid=(uri.scheme in ('postgres','postgresql') and
                (project_ref in (uri.username or '').lower() or
                 project_ref in (uri.hostname or '').lower()))
        except ValueError:
            valid=False
        if not valid:missing.append('REELBRAIN_DB_URL must target isolated Reelbrain project')
    mode=os.getenv('REELBRAIN_MEDIA_ACQUISITION','yt_dlp_public').lower().strip()
    if mode=='apify':
        if not flag('REELBRAIN_SOURCE_RIGHTS_CONFIRMED'):missing.append('REELBRAIN_SOURCE_RIGHTS_CONFIRMED')
        if not os.getenv('APIFY_API_TOKEN'):missing.append('APIFY_API_TOKEN')
        if not flag('REELBRAIN_PAID_PROVIDER_APPROVED'):missing.append('REELBRAIN_PAID_PROVIDER_APPROVED')
    elif mode=='yt_dlp_public':
        # Personal knowledge extraction from accessible public media is not
        # represented as copyright ownership. Never accept private/login-only
        # URLs or bypass permissions; acquisition remains best effort.
        if not (flag('REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED') or flag('REELBRAIN_SOURCE_RIGHTS_CONFIRMED')):
            missing.append('REELBRAIN_PERSONAL_KNOWLEDGE_USE_APPROVED')
        if not flag('REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD'):missing.append('REELBRAIN_ALLOW_PUBLIC_REEL_DOWNLOAD')
    else:missing.append('REELBRAIN_MEDIA_ACQUISITION (must be apify or yt_dlp_public)')
    if missing:raise RuntimeError('Worker will not claim jobs before configured: '+', '.join(missing))
    return {'db_url':os.environ['REELBRAIN_DB_URL'],
            'apify_token':os.getenv('APIFY_API_TOKEN',''), 'acquisition':mode}

def pg_open(db_url:str):
    try:import psycopg
    except ImportError as e:raise RuntimeError('Install psycopg[binary] in worker environment') from e
    return psycopg.connect(db_url,connect_timeout=6)

def reusable_hosted_audio(pg,source_url:str)->str|None:
    """Reuse the exact saved third-party transcript; never relabel it as local ASR."""
    with pg.cursor() as cur:
        cur.execute("select verified_reel_content->'provider_audio_transcript' "
                    "from public.reelbrain_reel_knowledge where source_url=%s",(source_url,))
        row=cur.fetchone()
    record=row[0] if row else None
    if not isinstance(record,dict) or record.get('provider') not in ('transcriptfetch','scrapecreators'):
        return None
    if record.get('source_type')!='third_party_asr_by_reel_url':
        return None
    if not isinstance(record.get('text'),str) or not record['text'].strip():
        return None
    segments=record.get('segments')
    if not isinstance(segments,list) or not segments or not any(
        isinstance(x,dict) and isinstance(x.get('text'),str) and x['text'].strip()
        for x in segments):
        return None
    return record['provider']


def process_url(source_url:str,pg,*,apify_token:str,acquisition:str='apify',lease=None)->dict:
    from tempfile import TemporaryDirectory
    from .public_bundle import acquire_public_bundle
    from .session_cookies import temporary_instagram_cookies
    hosted_audio=reusable_hosted_audio(pg,source_url) if acquisition=='yt_dlp_public' else None
    if lease:pg.commit()
    if hosted_audio:print('HOSTED_AUDIO_REUSED provider='+hosted_audio,flush=True)
    with TemporaryDirectory(prefix='rb_reel_worker_') as d:
        db=KnowledgeStore(Path(d)/'isolated_evidence.sqlite')
        try:
            def engine_factory(store):
                asr=None;vlm=None
                generic_external_allowed=flag('REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED')
                from .cloudflare_vision_config import cloudflare_qwen_config
                cf_vision=cloudflare_qwen_config()
                # Provider-specific Cloudflare vision opt-in must NOT silently
                # activate unrelated Groq paid ASR or Gemini model uploads.
                if not hosted_audio and generic_external_allowed and os.getenv('GROQ_API_KEY'):
                    asr=GroqSpeechToText(ProviderOptions(
                        os.environ['GROQ_API_KEY'],
                        os.getenv('GROQ_ASR_MODEL','whisper-large-v3-turbo'),
                        'https://api.groq.com'))
                if cf_vision:
                    from .qwen_vl import QwenVLResearcher
                    vlm=QwenVLResearcher(
                        cf_vision['base_url'],
                        model=cf_vision['model'],
                        api_key=cf_vision['api_key'],
                        max_frames=8)
                elif generic_external_allowed and os.getenv('REELBRAIN_QWEN_VL_BASE_URL'):
                    from .qwen_vl import QwenVLResearcher
                    vlm=QwenVLResearcher(
                        os.environ['REELBRAIN_QWEN_VL_BASE_URL'],
                        model=os.getenv('REELBRAIN_QWEN_VL_MODEL','Qwen/Qwen3-VL-8B-Instruct'),
                        api_key=os.getenv('REELBRAIN_QWEN_VL_API_KEY',''))
                elif generic_external_allowed and os.getenv('GEMINI_API_KEY'):
                    vlm=GeminiVideoResearcher(
                        os.environ['GEMINI_API_KEY'],
                        os.getenv('GEMINI_VIDEO_MODEL',''))
                if not hosted_audio and asr is None and flag('REELBRAIN_ENABLE_LOCAL_ASR'):
                    # Local Whisper executes fully on CPU, without any API upload.
                    from .local_asr import FasterWhisperSpeechToText
                    asr=FasterWhisperSpeechToText(
                        os.getenv('REELBRAIN_LOCAL_ASR_MODEL','small'))
                return LocalPipelineEngine(store,audio_model=asr,video_model=vlm)
            if acquisition=='yt_dlp_public':
                # Public-only: yt-dlp then gallery-dl fallback, or full photo
                # carousel. Every page must pass media-byte validation.
                # The optional user-managed session is a private, transient
                # alternative when Instagram rejects anonymous datacenter IPs.
                from .scrapecreators_media import acquire_with_public_provider
                with stage_slot('download'):
                    with temporary_instagram_cookies() as cookies:
                        bundle=acquire_with_public_provider(
                            source_url,Path(d),pg,cookies_file=cookies)
                if lease:pg.commit()
                print('MEDIA_ACQUIRED provider='+bundle.provider+
                      ' assets='+str(len(bundle.paths))+
                      ' bytes='+str(sum(p.stat().st_size for p in bundle.paths)),flush=True)
                print('VISUAL_ANALYSIS_STARTED',flush=True)
                with stage_slot('analysis'):
                    result=engine_factory(db).ingest(
                        list(bundle.paths),source_url,
                        allow_external=(flag('REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED')
                                        or flag('REELBRAIN_CLOUDFLARE_VISION_ENABLED')),
                        **({'checkpoint': lease_checkpoint(pg,lease,source_url,bundle.paths)} if lease else {}))
                result={**result,'media_processed':bool(result.get('processing_receipt_id')),
                        'provider':bundle.provider,'media_deleted_after_processing':True,
                        'hosted_audio_reused':hosted_audio}
            elif acquisition=='apify':
                result=process_instagram_link(db,source_url,
                    options=LinkProcessingOptions(allow_paid=True,allow_external=True,rights_confirmed=True),
                    apify_client=ApifyReelClient(apify_token),
                    downloader=SafeMediaDownloader(),engine_factory=engine_factory)
            else:raise RuntimeError('Unsupported media acquisition mode')
            if not result.get('media_processed'):
                raise RuntimeError('provider returned no locally processed media; refusing success status')
            print('MEDIA_ANALYSIS_FINISHED status='+str(result.get('status'))+
                  ' observation_counts='+json.dumps(result.get('stage_observations',{})),flush=True)
            with stage_slot('storage'):
                if lease:
                    with pg.transaction():
                        assert_lease(pg,lease)
                        saved=save_reel_to_postgres(db,pg,source_url,result)
                else:
                    saved=save_reel_to_postgres(db,pg,source_url,result)
            print('KNOWLEDGE_PERSISTED observations='+str(saved.get('observation_count',0))+
                  ' status='+str(saved.get('status')),flush=True)
            return saved
        finally:db.close()

def assert_lease(pg,lease):
    with pg.cursor() as cur:
        cur.execute("""select id from public.reelbrain_dm_jobs
            where id=%s and lease_token=%s and status='leased'
            and lease_until>now() for update""",lease)
        if not cur.fetchone():raise RuntimeError('lost lease before evidence write')


def lease_checkpoint(pg,lease,source_url,paths):
    from .stage_checkpoint import StageCheckpoint
    return StageCheckpoint(pg,lease,source_url,paths)


@contextmanager
def renewable_lease(config,job_id,token):
    """Renew using a separate connection; never share the worker transaction."""
    from threading import Event,Thread
    stop=Event()
    lost=Event()
    def heartbeat():
        while not stop.wait(60):
            try:
                with pg_open(config['db_url']) as conn:
                    with conn.cursor() as cur:
                        cur.execute("""update public.reelbrain_dm_jobs
                            set lease_until=now()+interval '15 minutes'
                            where id=%s and status='leased' and lease_token=%s
                            and lease_until>now() returning id""",(job_id,token))
                        if not cur.fetchone():
                            lost.set()
                            return
            except Exception:
                lost.set()
                return
    thread=Thread(target=heartbeat,daemon=True)
    thread.start()
    try:
        yield lost
    finally:
        stop.set()
        thread.join(timeout=10)


def run_one_batch(config:dict|None=None,batch_size:int=1,processor=None)->list[dict]:
    config=config or checked_config()
    with pg_open(config['db_url']) as pg:
        with pg.cursor() as cur:
            # A crashed or canceled runner is not a failed Reel. Recover
            # expired leases without consuming another source attempt.
            cur.execute("""update public.reelbrain_dm_jobs
                set status='queued', attempts=greatest(0,attempts-1),
                    lease_token=null,lease_until=null,available_at=now(),
                    updated_at=now(),last_error='Previous runner lease expired; resume pending stages'
                where status='leased' and lease_until<now()""")
            cur.execute('select id,source_url,lease_token from public.reelbrain_claim_dm_jobs(%s,%s)',(min(10,max(1,batch_size)),900))
            claimed=cur.fetchall()
        pg.commit()
        done=[]
        for job_id,url,token in claimed:
            try:
                if processor:
                    r=processor(url,pg)
                else:
                    with renewable_lease(config,job_id,token) as lost:
                        r=process_url(url,pg,apify_token=config['apify_token'],acquisition=config.get('acquisition','apify'),lease=(job_id,token))
                        if lost.is_set():raise RuntimeError('worker lease renewal lost')
                if not r.get('persisted_in_postgres'):raise RuntimeError('remote evidence persistence not confirmed')
                quota_retry=r.get('transient_model_retry_seconds')
                if r.get('status')=='partial' and quota_retry is None and r.get('incomplete_stages'):
                    quota_retry=3600
                if r.get('status')=='partial' and isinstance(quota_retry,int) and 900<=quota_retry<=86400:
                    # Model Neuron/ASR quota exhausted: preserve all saved
                    # evidence, then return the original source to the durable
                    # queue until capacity resets. Do NOT mark partial as
                    # terminal or burn finite source attempts on free quotas.
                    with pg.cursor() as cur:
                        cur.execute('select public.reelbrain_defer_dm_job(%s,%s,%s,%s)',
                                    (job_id,token,'Incomplete media stage; automatic retry',quota_retry))
                        ok=cur.fetchone()[0]
                    pg.commit()
                    if not ok:raise RuntimeError('Failed to acknowledge model quota deferral')
                    done.append({'id':job_id,'status':'deferred_model_quota',
                                 'source_url':url,'acknowledged_failure':True})
                    continue
                with pg.cursor() as cur:
                    cur.execute('select public.reelbrain_finish_dm_job(%s,%s,%s,%s::jsonb)',
                                (job_id,token,'partial' if r['status']=='partial' else 'processed',json.dumps(r)))
                    ok=cur.fetchone()[0]
                pg.commit()
                if not ok:raise RuntimeError('lost lease while finalizing durable job')
                done.append({'id':job_id,'status':r['status'],'source_url':url})
            except Exception as exc:
                from .access_backoff import access_backoff_seconds
                seconds_to_wait=access_backoff_seconds(exc)
                pg.rollback()
                reason=type(exc).__name__+': media worker stage incomplete'
                if seconds_to_wait is None:seconds_to_wait=3600
                with pg.cursor() as cur:
                    if seconds_to_wait is not None:
                        # A datacenter 403/429 must not burn a Reel's finite
                        # code-bug retries, or destroy recoverable public links.
                        cur.execute('select public.reelbrain_defer_dm_job(%s,%s,%s,%s)',
                                    (job_id,token,reason,seconds_to_wait))

                    ok=cur.fetchone()[0]
                pg.commit()
                done.append({'id':job_id,
                             'status':'deferred_access' if seconds_to_wait is not None else 'retry_or_dead_letter',
                             'source_url':url,'acknowledged_failure':bool(ok)})
        return done

def serve_forever():
    conf=checked_config() # fail before claiming any work
    idle=5
    while True:
        results=run_one_batch(conf)
        idle=5 if results else min(idle*1.5,60)
        time.sleep(idle) # sleeping idle, not spinning; true 24/7 requires host

if __name__=='__main__':serve_forever()
