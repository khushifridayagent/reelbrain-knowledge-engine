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
    from .qr_evidence import scan_video_qr
    result=[]
    for event in keyframes.analyse(str(path)):
        if not event.text.strip():continue
        minutes,seconds=divmod(float(event.t),60)
        result.append(Observation(event.text,kind='ocr',locator=f'{int(minutes):02}:{seconds:05.2f}',confidence=max(0,min(float(event.conf),100))/100))
    qr_evidence,coverage=scan_video_qr(path)
    # Scanning beyond the bounded video window never fabricates full coverage.
    # Ordinary OCR evidence remains intact even when there is no QR.
    result.extend(qr_evidence)
    return result


class LocalPipelineEngine:
    def __init__(self,store:KnowledgeStore, *, ocr:Callable[[Path],list[Observation]]|None=None,
                 audio_model=None,video_model=None,audio_extractor=None,fact_model=None,native_ocr=None):
        self.store=store
        self.ocr=ocr or adaptive_local_ocr
        self.audio_model=audio_model
        self.video_model=video_model
        self.audio_extractor=audio_extractor
        self.fact_model=fact_model
        self.native_ocr=native_ocr

    def _transcribe(self,media:Path):
        from .media import extract_audio
        with tempfile.TemporaryDirectory(prefix='rb_audio_') as td:
            audio=self.audio_extractor(media) if self.audio_extractor else extract_audio(media,Path(td)/'sound.wav')
            return self.audio_model.transcribe(Path(audio))

    def ingest(self,media_path:str|Path|list[Path]|tuple[Path,...],source_url:str,
               tenant:str='personal',allow_external:bool=False,
               extra_observations:list[Observation]|None=None,checkpoint=None)->dict:
        """Ingest a single video or a full 1–20-page mixed carousel.

        Each slide keeps its own evidence locator; one canonical source and
        receipt represent the complete ordered bundle.
        """
        inputs = list(media_path) if isinstance(media_path,(list,tuple)) else [media_path]
        if not 1 <= len(inputs) <= 20:raise ValueError('media bundle must contain 1–20 assets')
        media_assets = [Path(p) for p in inputs]
        for asset in media_assets:
            if not asset.is_file():raise FileNotFoundError(asset)
        if sum(p.stat().st_size for p in media_assets)>350*1024*1024:
            raise ValueError('local media bundle over 350MB budget')
        media=media_assets[0]
        source=canonicalize_instagram(source_url)
        # Local CPU Whisper is genuinely offline. Only adapters that could
        # transfer audio/video to another host need an external-upload opt-in.
        # Treat adapters without an explicit marker as remote by default.
        video_assets=[p for p in media_assets if p.suffix.lower() in {'.mp4','.mov','.mkv','.webm','.avi'}]
        if self.native_ocr is not None:
            from .native_hybrid import has_audio_stream
            video_assets=[p for p in video_assets if has_audio_stream(p)]
        video_present=bool(video_assets)
        adapters=(
            (self.audio_model,video_present),
            (self.video_model,True),
            (self.fact_model,True),
        )
        external_count=sum(int(adapter is not None and active and
                               getattr(adapter,'requires_external',True))
                           for adapter,active in adapters)
        if external_count and not allow_external:
            raise RemoteConsentRequired('remote audio/video/model transfer requires explicit --allow-external')
        slide_failures=[]
        def read_all_pages():
            observations=[]
            for idx,asset in enumerate(media_assets,1):
                try:
                    found=(self.native_ocr.analyze(asset,checkpoint=checkpoint,asset_index=idx)
                           if self.native_ocr is not None else self.ocr(asset))
                    if not isinstance(found,list):raise TypeError('OCR output must be a list')
                    for ev in found:
                        if not isinstance(ev,Observation):raise TypeError('OCR output must contain typed observations')
                        locator=(f'slide:{idx:02d}/'+ev.locator) if len(media_assets)>1 else ev.locator
                        observations.append(Observation(ev.text,kind=ev.kind,locator=locator,confidence=ev.confidence))
                except Exception as exc:
                    if self.native_ocr is not None:
                        from .native_hybrid import NativeInspectionPending
                        for ev in getattr(exc,'partial_observations',[]):
                            loc=(f'slide:{idx:02d}/'+ev.locator) if len(media_assets)>1 else ev.locator
                            observations.append(Observation(ev.text,kind=ev.kind,locator=loc,confidence=ev.confidence))
                        raise NativeInspectionPending('native OCR incomplete; resume saved chunks',observations) from None
                    if len(media_assets)==1:raise
                    slide_failures.append(f'slide:{idx:02d}:{type(exc).__name__}')
            return observations
        def transcribe_all():
            observations=[]
            for idx,asset in enumerate(media_assets,1):
                if asset not in video_assets:continue
                for ev in self._transcribe(asset):
                    locator=(f'slide:{idx:02d}/'+ev.locator) if len(media_assets)>1 else ev.locator
                    observations.append(Observation(ev.text,kind=ev.kind,locator=locator,confidence=ev.confidence))
            return observations
        visual_coverage_gaps=[]
        def video_understanding():
            from .qwen_vl import QwenPartialVisualError,QwenVLResearcher
            observations=[]
            for idx,asset in enumerate(media_assets,1):
                # Every static carousel slide gets its own visual pass; no
                # hallucination from speech can stand in for missing pages.
                def add_results(events):
                    for ev in events:
                        if not isinstance(ev,Observation):
                            raise TypeError('Visual model returned an invalid observation')
                        locator=(f'slide:{idx:02d}/'+ev.locator) if len(media_assets)>1 else ev.locator
                        observations.append(Observation(
                            ev.text,kind='model_inference',
                            locator=locator,confidence=ev.confidence))
                try:
                    if checkpoint is not None and (isinstance(self.video_model,QwenVLResearcher) or getattr(self.video_model,'supports_checkpoint',False) is True):
                        add_results(self.video_model.analyze(asset,checkpoint=checkpoint,asset_index=idx))
                    else:
                        add_results(self.video_model.analyze(asset))
                    stats=getattr(self.video_model,'sampling_stats',None)
                    if isinstance(stats,dict) and stats.get('partial_scan'):
                        visual_coverage_gaps.append(
                            f"asset:{idx:02d}:sampled:{int(stats.get('selected_scenes') or 0)}"
                            f":candidate:{int(stats.get('candidate_scenes') or 0)}")
                except Exception as exc:
                    partial=getattr(exc,'partial_observations',None)
                    if isinstance(partial,list):
                        add_results(partial)
                    # VLM over-quota after a page MUST NOT wipe earlier
                    # successful image inferences, nor independently decoded
                    # source OCR/QR evidence. Never leak raw provider errors.
                    category='quota exceeded' if 'quota' in str(exc).lower() else (
                        'service unavailable' if 'unavailable' in str(exc).lower()
                        else 'visual model request failed')
                    if isinstance(exc,QwenPartialVisualError):category=str(exc)
                    raise QwenPartialVisualError(category,observations) from None
            return observations
        tasks={'ocr':read_all_pages}
        if self.audio_model is not None and video_assets:tasks['asr']=transcribe_all
        if self.video_model is not None:tasks['vlm']=video_understanding
        measurements={};errors={};results={}
        def timed(label,func):
            start=time.monotonic()
            try:return func(),int((time.monotonic()-start)*1000)
            except Exception:raise
        def stage_unit(label):
            if label=='ocr' and self.native_ocr is not None:return 'native-hybrid-v1:full-ocr'
            if label=='vlm' and getattr(self.video_model,'supports_checkpoint',False) is True:return 'native-hybrid-v1:full-vlm'
            return None
        if checkpoint:
            for label in list(tasks):
                unit=stage_unit(label)
                cached=checkpoint.load(label,unit=unit) if unit else checkpoint.load(label)
                if cached is not None:
                    results[label],measurements[label]=cached
                    del tasks[label]
        with ThreadPoolExecutor(max_workers=max(1,len(tasks))) as pool:
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
                    # Keep completed visual batches when the shared Cloudflare
                    # Neuron allocation runs out halfway through a Reel.
                    if stage=='ocr' and self.native_ocr is not None:
                        partial=getattr(exc,'partial_observations',None)
                        if isinstance(partial,list) and all(isinstance(ev,Observation) and ev.kind in ('ocr','qr','ocr_uncertain') for ev in partial):
                            results[stage]=partial
                    if stage=='vlm':
                        partial=getattr(exc,'partial_observations',None)
                        if isinstance(partial,list) and all(
                            isinstance(ev,Observation) and ev.kind=='model_inference'
                            for ev in partial):
                            results[stage]=partial[:120]
                    errors[stage]=f'{type(exc).__name__}: {exc}'[:250]
                if checkpoint and stage in results and stage not in errors and not (
                    (stage=='ocr' and slide_failures) or (stage=='vlm' and visual_coverage_gaps)):
                    unit=stage_unit(stage)
                    if unit:checkpoint.save(stage,results[stage],measurements[stage],unit=unit)
                    else:checkpoint.save(stage,results[stage],measurements[stage])
        if slide_failures:
            errors['ocr']='OCR failed on '+','.join(slide_failures[:20])
        if visual_coverage_gaps:
            # 32 selected scenes do not mean every fast-changing visual state
            # was understood. Keep the correct partial status for follow-up.
            errors['visual_coverage']='Qwen scene sample budget left gaps: '+','.join(visual_coverage_gaps[:20])
        extra=list(extra_observations or [])
        if not all(isinstance(ev,Observation) and ev.kind in ('caption','asr','manual','document') for ev in extra):
            raise ValueError('external observations must be typed source evidence, not model output')
        observations=sum((results.get(name,[]) for name in ('ocr','asr','vlm')),[])+extra
        candidates=[candidate for item in observations for candidate in candidate_urls(item.text)]
        pipe=KnowledgePipeline(self.store)
        source_name=('bundle:'+source) if len(media_assets)>1 else media.name
        saved=pipe.ingest_evidence(source_name,source,'reel' if '/reel/' in source else 'carousel',observations,candidates,tenant=tenant)
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
        original_evidence=any(ev.kind in {'ocr','qr','asr','caption','manual','verified_doc'}
                              and ev.text.strip() for ev in observations)
        model_only_evidence=any(ev.kind=='model_inference' and ev.text.strip()
                                for ev in observations)
        if not original_evidence:
            if model_only_evidence:
                # Media was actually provided, and the model generated useful
                # descriptions. Save as explicitly *partial* inference only;
                # no inferred URL can become an independently proven resource.
                errors['no_source_evidence']='visual inference only; OCR/ASR source observations absent'
            else:
                errors['all_passes']='no source observations or visual inference; media remains pending'
        saved['status']='partial' if errors else 'evidence_saved'
        self.store.con.execute('UPDATE sources SET status=? WHERE id=? AND tenant=?',
                               (saved['status'],saved['source_id'],tenant))
        if original_evidence or model_only_evidence:
            sha=hashlib.sha256()
            for asset in media_assets:
                with asset.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''):
                        sha.update(chunk)
            link_id=pipe.ingest_url(source,tenant)['source_id']
            receipt=self.store.mark_media_processed(
                tenant,link_id,saved['source_id'],sha.hexdigest(),
                partial=bool(errors),
                model_only_partial=bool(model_only_evidence and not original_evidence))
            saved['processing_receipt_id']=receipt
            saved['media_sha256']=sha.hexdigest()
        saved.update({'stage_errors':errors,'stage_timings_ms':measurements,'stage_observations':{**{k:len(v) for k,v in results.items()},'provided':len(extra)},'external_calls':external_count,'media_is_local':True,
                      'knowledge_completeness':'NOT_AUDITED','asset_count':len(media_assets),'audio_required':bool(video_assets),
                      'unattempted_modalities':([stage for stage,active in (('asr',self.audio_model is not None),('video_model',self.video_model is not None),('structured_fact_model',self.fact_model is not None)) if not active])})
        return saved
