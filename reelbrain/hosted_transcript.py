"""Opt-in URL-first speech provider; no Instagram video upload in GitHub.

Paid credits are NEVER used unless both explicit approval flags and an API key
are configured. Returned text is labeled third-party ASR, not independently
observed audio/frames. Database queues continue awaiting video OCR/VLM.
"""
from __future__ import annotations
import math
import os
from typing import Any
from .sources import canonicalize_instagram


class TranscriptProviderError(RuntimeError):
    """Sanitized, user-safe external speech API failure."""


def hosted_transcript_enabled() -> bool:
    provider=os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_PROVIDER','scrapecreators').strip().lower()
    key_name={'scrapecreators':'REELBRAIN_TRANSCRIPT_API_KEY',
              'transcriptfetch':'TRANSCRIPTFETCH_API_KEY'}.get(provider)
    return (
        bool(key_name)
        and os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_ENABLED') == '1'
        and os.environ.get('REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED') == '1'
        and bool(os.environ.get(key_name,''))
    )


def normalize_transcript(url: str, data: Any) -> dict | None:
    """Validate caption-independent speech text and optional timing.

    No model-generated summary or metadata caption is upgraded to a source
    speech transcript. Verify stable shortcodes; never echo raw provider errors.
    """
    canonical=canonicalize_instagram(url)
    shortcode=canonical.rstrip('/').rsplit('/',1)[-1]
    if not isinstance(data,dict) or data.get('success') is not True:
        raise TranscriptProviderError('Hosted transcript provider returned failure')
    rows=data.get('transcripts')
    if not isinstance(rows,list) or len(rows)>20:
        raise TranscriptProviderError('Hosted transcript response has invalid item count')
    if not rows:return None
    phrases=[]
    segments=[]
    for page,entry in enumerate(rows,1):
        if not isinstance(entry,dict) or str(entry.get('shortcode') or '') != shortcode:
            raise TranscriptProviderError('Hosted transcript shortcode does not match requested Reel')
        text=entry.get('text')
        if text is not None and not isinstance(text,str):
            raise TranscriptProviderError('Hosted transcript text must be a string or null')
        if text is None or not text.strip():
            continue
        if len(text)>60000:
            raise TranscriptProviderError('Hosted transcript exceeds storage budget')
        phrases.append(text.strip())
        timed=entry.get('transcript_with_timestamp')
        if timed is None:
            continue
        if not isinstance(timed,list) or len(timed)>500:
            raise TranscriptProviderError('Hosted transcript timestamps are malformed')
        for item in timed:
            if not isinstance(item,dict):raise TranscriptProviderError('Timestamp item malformed')
            start,end=item.get('start'),item.get('end')
            words=item.get('text')
            if (not isinstance(start,(int,float)) or isinstance(start,bool)
                or not isinstance(end,(int,float)) or isinstance(end,bool)
                or not math.isfinite(start) or not math.isfinite(end)
                or start<0 or end<start or end>7200 or not isinstance(words,str)):
                raise TranscriptProviderError('Timestamp values malformed')
            if words.strip():
                segments.append({'slide_index':page,'start':round(float(start),3),
                                 'end':round(float(end),3),'text':words.strip()[:2000]})
    if not phrases:return None
    if sum(map(len,phrases))>60000:
        raise TranscriptProviderError('Hosted transcript exceeds bounded output')
    return {'provider':'scrapecreators','source_url':canonical,
            'shortcode':shortcode,'text':'\n'.join(phrases),
            'segments':segments[:500],
            'provenance':'hosted_ai_speech_transcript_by_url',
            'first_party_media_verified':False,
            'visual_frames_verified':False}


class HostedTranscriptClient:
    ENDPOINT='https://api.scrapecreators.com/v2/instagram/media/transcript'
    def __init__(self,api_key:str,*,http=None):
        if not api_key:
            raise ValueError('Hosted transcript API key required')
        self._api_key=api_key
        self.http=http

    def fetch(self,url:str)->dict|None:
        import httpx
        canonical=canonicalize_instagram(url)
        try:
            response=(self.http or httpx).get(
                self.ENDPOINT,
                headers={'x-api-key':self._api_key,'Accept':'application/json'},
                params={'url':canonical,'allow_long_transcription':'false',
                        'cache_max_age':'30d'},
                timeout=55,
            )
            response.raise_for_status()
            data=response.json()
        except Exception as exc:
            # Do not record request URLs containing private query strings,
            # raw response bodies, API keys or provider stack traces.
            raise TranscriptProviderError('Hosted transcript request failed: '+
                                          type(exc).__name__) from None
        return normalize_transcript(canonical,data)
