"""Three-pass local ingest. External model uploads require explicit per-run consent.

Pass A: opt-in multimodal VLM, label as *model inference*, never primary proof.
Pass B: opt-in timestamped ASR; verbatim transcript is source evidence.
Pass C: local, deterministic adaptive frame OCR from original reelbrain core.

Partial pass failures preserve all successful observations. This is not an
Instagram downloader and does not start background tasks by itself.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
import tempfile, time, hashlib
from .contracts import Observation, candidate_urls, evidence_filter
from .pipeline import KnowledgePipeline
from .sources import canonicalize_instagram
from .store import KnowledgeStore

class RemoteConsentRequired(PermissionError):pass


def adaptive_local_ocr(path:Path)->list[Observation]:
    from .media import recognize_image
    if path.suffix.lower() not in {'.mp4','.mov','.avi','.mkv','.webm'}:
        return recognize_image(path)
    from . import keyframes
    result=[]
    for event in keyframes.analyse(str(path)):
        if not event.text.strip():continue
        minutes,seconds=divmod(float(event.t),60)
        result.append(Observation(event.text,kind='ocr',locator=f'{int(minutes):02}:{seconds:05.2f}',confidence=max(0,min(float(event.conf),100))/100))
    return result


class LocalPipelineEngine:
    def __init__(self,store:KnowledgeStore, *, ocr:Callable[[Path],list[Observation]]|None=None,
                 audio_model=None,video_model=None,audio_extractor=None,fact_model=None):
        self.store=store
        self.ocr=ocr or adaptive_local_ocr
        self.audio_model=audio_model
        self.video_model=video_model
        self.audio_extractor=audio_extractor
        self.fact_model=fact_model

    def _transcribe(self,media:Path):
        from .media import extract_audio
        with tempfile.TemporaryDirectory(prefix='rb_audio_') as td:
            audio=self.audio_extractor(media) if self.audio_extractor else extract_audio(media,Path(td)/'sound.wav')
            return self.audio_model.transcribe(Path(audio))

    def ingest(self,media_path:str|Path,source_url:str,tenant:str='personal',allow_external:bool=False,
               extra_observations:list[Observation]|None=None)->dict:
        media=Path(media_path)
        if not media.is_file():raise FileNotFoundError(media)
        if media.stat().st_size>350*1024*1024:raise ValueError('local media over 350MB budget')
        source=canonicalize_instagram(source_url)
        external_count=int(self.audio_model is not None)+int(self.video_model is not None)+int(self.fact_model is not None)
        if external_count and not allow_external:
            raise RemoteConsentRequired('audio/video uploads require explicit --allow-external')
        tasks={'ocr':lambda:self.ocr(media)}
        if self.audio_model is not None:tasks['asr']=lambda:self._transcribe(media)
        if self.video_model is not None:tasks['vlm']=lambda:self.video_model.analyze(media)
        measurements={};errors={};results={}
        def timed(label,func):
            start=time.monotonic()
            try:return func(),int((time.monotonic()-start)*1000)
            except Exception:raise
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
            pending={pool.submit(timed,label,fn):label for label,fn in tasks.items()}
            for future in as_completed(pending):
                stage=pending[future]
                try:
                    raw,elapsed=future.result()
                    if not isinstance(raw,list) or not all(isinstance(e,Observation) for e in raw):
                        raise TypeError('provider must return list[Observation]')
                    # Model text is never proof even when a provider mislabels it.
                    if stage=='vlm':
                        raw=[Observation(e.text,kind='model_inference',locator=e.locator,confidence=e.confidence) for e in raw]
                    results[stage]=raw
                    measurements[stage]=elapsed
                except Exception as exc:
                    errors[stage]=f'{type(exc).__name__}: {exc}'[:250]
        extra=list(extra_observations or [])
        if not all(isinstance(ev,Observation) and ev.kind in ('caption','asr','manual','document') for ev in extra):
            raise ValueError('external observations must be typed source evidence, not model output')
        observations=sum((results.get(name,[]) for name in ('ocr','asr','vlm')),[])+extra
        candidates=[candidate for item in observations for candidate in candidate_urls(item.text)]
        pipe=KnowledgePipeline(self.store)
        saved=pipe.ingest_evidence(media.name,source,'reel' if '/reel/' in source else 'carousel',observations,candidates,tenant=tenant)
        saved['facts_accepted']=0
        saved['facts_rejected']=[]
        if self.fact_model is not None and observations:
            start=time.monotonic()
            try:
                verified=evidence_filter(candidates,observations)
                supported={c.url for c in verified.accepted}
                valid,rejected=self.fact_model.extract(observations,supported)
                saved['facts_rejected']=rejected
                stored=pipe.add_claims(saved['source_id'],observations,valid,tenant=tenant)
                saved['facts_accepted']=stored['accepted']
                saved['facts_rejected']+=stored['rejected']
                measurements['fact_enrichment']=int((time.monotonic()-start)*1000)
            except Exception as exc:
                errors['fact_enrichment']=f'{type(exc).__name__}: {exc}'[:250]
        original_evidence=any(ev.kind in {'ocr','asr','caption','manual','verified_doc'} and ev.text.strip() for ev in observations)
        if not original_evidence:
            errors['all_passes']='no non-generative source observations; Reel remains pending'
        saved['status']='partial' if errors else 'evidence_saved'
        self.store.con.execute('UPDATE sources SET status=? WHERE id=? AND tenant=?',
                               (saved['status'],saved['source_id'],tenant))
        if original_evidence:
            sha=hashlib.sha256()
            with media.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    sha.update(chunk)
            link_id=pipe.ingest_url(source,tenant)['source_id']
            receipt=self.store.mark_media_processed(tenant,link_id,saved['source_id'],sha.hexdigest(),partial=bool(errors))
            saved['processing_receipt_id']=receipt
        saved.update({'stage_errors':errors,'stage_timings_ms':measurements,'stage_observations':{**{k:len(v) for k,v in results.items()},'provided':len(extra)},'external_calls':external_count,'media_is_local':True,
                      'knowledge_completeness':'NOT_AUDITED',
                      'unattempted_modalities':([stage for stage,active in (('asr',self.audio_model is not None),('video_model',self.video_model is not None),('structured_fact_model',self.fact_model is not None)) if not active])})
        return saved
