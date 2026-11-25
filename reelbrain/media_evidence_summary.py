"""Typed Reel media evidence projection for private Postgres knowledge rows.

Only actual OCR/ASR source observations are source evidence. VLM text remains
model inference. All observations are bounded and preserve timestamp locators.
An observed Reel is NOT independently verified by an LLM.
"""
from __future__ import annotations

SOURCE_KINDS = {'ocr', 'qr', 'asr', 'caption', 'manual', 'document', 'verified_doc'}


def build_media_summary(observations: list[dict], result: dict) -> dict:
    if not isinstance(result, dict):
        raise TypeError('Worker result must be a dict')
    media_processed = result.get('media_processed') is True
    counts = result.get('stage_observations', {}) or {}
    if not isinstance(counts, dict):
        counts = {}
    errors = result.get('stage_errors', {}) or {}
    if not isinstance(errors, dict):
        errors = {}
    source = []
    model = []
    for ev in observations:
        if len(source)>=80 and len(model)>=80:break
        if not isinstance(ev, dict):
            continue
        kind = str(ev.get('kind', 'unknown'))[:32]
        text = str(ev.get('verbatim') or '')[:4000].strip()
        locator = str(ev.get('locator') or 'unlocated')[:64]
        if not text:
            continue
        row = {'kind': kind, 'locator': locator, 'text': text,
               'evidence_level': 'source_observation' if kind in SOURCE_KINDS else ('uncertain_source_observation' if kind=='ocr_uncertain' else 'model_inference')}
        target = source if kind in SOURCE_KINDS or kind=='ocr_uncertain' else model
        if len(target) < 80:
            target.append(row)
    ocr_succeeded = media_processed and 'ocr' in counts and 'ocr' not in errors
    asr_succeeded = media_processed and 'asr' in counts and 'asr' not in errors
    # This flag records that real acquired media received a successful visual
    # pass, including a labeled VLM inference; it is never external factual
    # verification. Separate source_observations and model_inferences below.
    vlm_succeeded = media_processed and int(counts.get('vlm') or 0)>0 and 'vlm' not in errors
    video_analyzed = (ocr_succeeded and int(counts.get('ocr') or 0) > 0) or vlm_succeeded
    from .resumable_media import required_incomplete_stages
    hosted_audio = result.get('hosted_audio_reused') in ('transcriptfetch','scrapecreators')
    audio_ready = not result.get('audio_required',True) or hosted_audio or (asr_succeeded and int(counts.get('asr') or 0)>0)
    complete = (media_processed and result.get('status')=='evidence_saved' and
                not required_incomplete_stages(result) and ocr_succeeded and vlm_succeeded and
                audio_ready and bool(observations))
    assets=result.get('asset_count')
    assets=assets if type(assets) is int and 1<=assets<=20 else None
    return {
        'video_analyzed': video_analyzed,
        'audio_transcribed': asr_succeeded and int(counts.get('asr') or 0) > 0,
        'ocr_analyzed': ocr_succeeded,
        'processing_stage': 'completed' if complete else ('partial_media' if media_processed else 'media_pending'),
        'content': {
            'media_accessed': media_processed,
            'asset_count': assets,
            'completed_asset_count': assets if complete else None,
            'hosted_audio_reused': result.get('hosted_audio_reused') if result.get('hosted_audio_reused') in ('transcriptfetch','scrapecreators') else None,
            'source_observations': source,
            'model_inferences': model,
            'source_id': str(result.get('source_id') or '')[:200],
            'media_provider': str(result.get('provider') or '')[:100],
            'stage_observations': {str(k)[:30]: int(v) for k, v in counts.items() if isinstance(v, (int, float))},
            'stage_errors': {str(k)[:30]: str(v)[:240] for k, v in errors.items()},
            'optional_stage_errors': {str(k)[:30]: str(v)[:240] for k,v in (result.get('optional_stage_errors') or {}).items()},
            'unattempted_modalities': list(result.get('unattempted_modalities', []))[:10],
            'completeness': 'NOT_AUDITED',
            'verification_note': 'OCR/ASR are source observations; Gemini/VLM descriptions are model inference only. External claims are not independently verified.'
        }
    }