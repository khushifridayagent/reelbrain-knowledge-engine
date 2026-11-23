"""Explicitly authorized, single-Reel external acquisition -> local 3-pass engine.

A URL alone is not a video. Paid account activity, rights, external transfers,
source identity and actual-media receipt are checked independently.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import tempfile
from .acquire_apify import ApifyReelClient,AcquisitionError,SafeMediaDownloader
from .contracts import Observation,candidate_urls
from .pipeline import KnowledgePipeline
from .sources import canonicalize_instagram
from .engine import LocalPipelineEngine
from .store import KnowledgeStore

@dataclass(frozen=True)
class LinkProcessingOptions:
    allow_paid:bool=False
    allow_external:bool=False
    rights_confirmed:bool=False
    tenant:str='personal'


def _metadata_only(store:KnowledgeStore,url:str,tenant:str,caption:str,reason:str)->dict:
    evidence=[Observation(caption,kind='caption',locator='apify:caption')] if caption.strip() else []
    pipe=KnowledgePipeline(store)
    # Persist explicit provenance even if no video is accessible.
    saved=pipe.ingest_evidence('remote_caption',url,'reel',evidence,
              [c for ev in evidence for c in candidate_urls(ev.text)],tenant=tenant)
    store.con.execute('UPDATE sources SET status=? WHERE id=? AND tenant=?',
                      ('partial_metadata_only',saved['source_id'],tenant))
    return {**saved,'status':'partial_metadata_only','media_processed':False,
            'media_error':reason,'media_deleted_after_processing':True,'provider_runs':1,
            'knowledge_completeness':'NOT_AUDITED',
            'note':'A provider caption is not proof that video/audio/frames were processed.'}


def process_instagram_link(store:KnowledgeStore,url:str,*,options:LinkProcessingOptions,
                           apify_client:ApifyReelClient,downloader:SafeMediaDownloader,
                           engine_factory=None)->dict:
    """Paid per-Reel stage; call-site must enforce credentials and explicit rights.

    On failed video acquisition, retain only clearly labelled provider metadata.
    Temporary original media is deleted on all paths, including engine errors.
    """
    if not (options.allow_paid and options.allow_external and options.rights_confirmed):
        raise PermissionError('Need --allow-external, --allow-paid and --rights-confirmed before any provider call')
    canonical=canonicalize_instagram(url)
    if '/reel/' not in canonical:
        raise AcquisitionError('Only /reel/ links accepted by this provider adapter')
    post=apify_client.inspect(canonical,allow_paid=True)
    if post.url!=canonical or post.shortcode!=canonical.rstrip('/').split('/')[-1]:
        raise AcquisitionError('provider returned a different Reel identity')
    caption=Observation(post.caption,kind='caption',locator='apify:caption') if post.caption.strip() else None
    if not post.media_url:
        return _metadata_only(store,canonical,options.tenant,post.caption,'video_url_unavailable')
    with tempfile.TemporaryDirectory(prefix='reelbrain_authorized_download_') as td:
        media=Path(td)/'original.mp4'
        try:
            downloaded=downloader.download(post.media_url,media)
        except AcquisitionError as exc:
            return _metadata_only(store,canonical,options.tenant,post.caption,
                                  f'{type(exc).__name__}: {exc}'[:250])
        engine=engine_factory(store) if engine_factory else LocalPipelineEngine(store)
        result=engine.ingest(downloaded,canonical,options.tenant,
                             allow_external=options.allow_external,
                             extra_observations=[caption] if caption else [])
        return {**result,'media_processed':bool(result.get('processing_receipt_id')),
                'media_deleted_after_processing':True,'provider_runs':1,
            'knowledge_completeness':'NOT_AUDITED',
                'provider':'apify/instagram-reel-scraper',
                'note':'Full video content claims require separately tested OCR/ASR/VLM passes.'}
