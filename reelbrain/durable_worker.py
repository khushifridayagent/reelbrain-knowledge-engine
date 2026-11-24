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

def process_url(source_url:str,pg,*,apify_token:str,acquisition:str='apify')->dict:
    from tempfile import TemporaryDirectory
    from .public_bundle import acquire_public_bundle
    from .session_cookies import temporary_instagram_cookies
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
                if generic_external_allowed and os.getenv('GROQ_API_KEY'):
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
                if asr is None and flag('REELBRAIN_ENABLE_LOCAL_ASR'):
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
                with temporary_instagram_cookies() as cookies:
                    bundle=acquire_public_bundle(source_url,Path(d),cookies_file=cookies)
                result=engine_factory(db).ingest(
                    list(bundle.paths),source_url,
                    allow_external=(flag('REELBRAIN_EXTERNAL_MODEL_UPLOAD_ALLOWED')
                                    or flag('REELBRAIN_CLOUDFLARE_VISION_ENABLED')))
                result={**result,'media_processed':bool(result.get('processing_receipt_id')),
                        'provider':bundle.provider,'media_deleted_after_processing':True}
            elif acquisition=='apify':
                result=process_instagram_link(db,source_url,
                    options=LinkProcessingOptions(allow_paid=True,allow_external=True,rights_confirmed=True),
                    apify_client=ApifyReelClient(apify_token),
                    downloader=SafeMediaDownloader(),engine_factory=engine_factory)
            else:raise RuntimeError('Unsupported media acquisition mode')
            if not result.get('media_processed'):
                raise RuntimeError('provider returned no locally processed media; refusing success status')
            return save_reel_to_postgres(db,pg,source_url,result)
        finally:db.close()

def run_one_batch(config:dict|None=None,batch_size:int=1,processor=None)->list[dict]:
    config=config or checked_config()
    with pg_open(config['db_url']) as pg:
        with pg.cursor() as cur:
            cur.execute('select public.reelbrain_reap_expired_dm_jobs(%s)',(100,))
            cur.execute('select id,source_url,lease_token from public.reelbrain_claim_dm_jobs(%s,%s)',(min(10,max(1,batch_size)),900))
            claimed=cur.fetchall()
        pg.commit()
        done=[]
        for job_id,url,token in claimed:
            try:
                r=processor(url,pg) if processor else process_url(url,pg,apify_token=config['apify_token'],acquisition=config.get('acquisition','apify'))
                if not r.get('persisted_in_postgres'):raise RuntimeError('remote evidence persistence not confirmed')
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
                reason=(type(exc).__name__+': '+str(exc))[:350]
                with pg.cursor() as cur:
                    if seconds_to_wait is not None:
                        # A datacenter 403/429 must not burn a Reel's finite
                        # code-bug retries, or destroy recoverable public links.
                        cur.execute('select public.reelbrain_defer_dm_job(%s,%s,%s,%s)',
                                    (job_id,token,reason,seconds_to_wait))
                    else:
                        cur.execute('select public.reelbrain_fail_dm_job(%s,%s,%s)',
                                    (job_id,token,reason))
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
