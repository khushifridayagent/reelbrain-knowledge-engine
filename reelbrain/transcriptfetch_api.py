"""TranscriptFetch v2 URL-only Instagram spoken-word extraction.

The provider obtains audio externally: Reelbrain never claims first-party
video frames or video verification from this transcript. Zero network calls
unless its separate budget/enable gates and bearer secret are configured.
"""
from __future__ import annotations

import math
import re

from .sources import canonicalize_instagram


class TranscriptFetchError(RuntimeError):
    """Safe external-provider error category, without URL or bearer token."""


BASE='https://transcriptfetch.com'
JOB_RE=re.compile(r'^asr_[A-Za-z0-9_-]{3,80}$')


def validate_poll_id(job_id:str)->str:
    if not isinstance(job_id,str) or not JOB_RE.fullmatch(job_id):
        raise TranscriptFetchError('Invalid transcript job identifier')
    return job_id


def normalize_transcriptfetch(url:str,payload:dict)->dict|None:
    original=canonicalize_instagram(url)
    shortcode=original.rstrip('/').rsplit('/',1)[-1]
    if not isinstance(payload,dict) or payload.get('ok') is not True:
        raise TranscriptFetchError('Unexpected transcript result envelope')
    data=payload.get('data')
    if not isinstance(data,dict) or data.get('kind','transcript')!='transcript':
        raise TranscriptFetchError('Transcript payload missing')
    if data.get('platform')!='instagram':
        raise TranscriptFetchError('Requested platform differs from returned media')
    observed=data.get('video_id')
    if not isinstance(observed,str):
        raise TranscriptFetchError('Missing transcript media identity')
    if 'instagram.com/' in observed or 'instagr.am/' in observed:
        try:observed=canonicalize_instagram(observed).rstrip('/').rsplit('/',1)[-1]
        except Exception:raise TranscriptFetchError('Invalid transcript media identity') from None
    if shortcode!=observed:
        raise TranscriptFetchError('Transcript belongs to another Reel')
    if data.get('source')!='audio':
        raise TranscriptFetchError('Returned text is not audio transcription')
    text=data.get('text')
    if text is not None and not isinstance(text,str):
        raise TranscriptFetchError('Transcript size/type out of allowed range')
    segments_raw=data.get('segments') or []
    if not isinstance(segments_raw,list) or len(segments_raw)>1000:
        raise TranscriptFetchError('Transcript segments malformed')
    segments=[]
    for seg in segments_raw:
        if not isinstance(seg,dict):
            raise TranscriptFetchError('Transcript segment malformed')
        start,duration=seg.get('start'),seg.get('duration')
        spoken=seg.get('text')
        if (not isinstance(start,(int,float)) or isinstance(start,bool)
            or not isinstance(duration,(int,float)) or isinstance(duration,bool)
            or not math.isfinite(start) or not math.isfinite(duration)
            or start<0 or duration<0 or start+duration>7200
            or not isinstance(spoken,str)):
            raise TranscriptFetchError('Transcript segment timing malformed')
        if spoken.strip():
            segments.append({'start':round(float(start),3),
                             'end':round(float(start+duration),3),
                             'text':spoken.strip()[:3000]})
    # TranscriptFetch's documented timestamps=true response omits the
    # redundant full 'text' field and returns just timestamped segments.
    # Never discard real spoken text solely because 'text' was omitted.
    if not (text or '').strip():
        text=' '.join(segment['text'] for segment in segments)
    if not text.strip():
        return None
    if len(text)>90000:
        raise TranscriptFetchError('Transcript exceeds bounded storage budget')
    return {'provider':'transcriptfetch','source_url':original,
            'shortcode':shortcode,'text':text.strip(),
            'segments':segments,'provenance':'hosted_ai_speech_transcript_by_url',
            'first_party_media_verified':False,'visual_frames_verified':False}


class TranscriptFetchClient:
    def __init__(self,api_key:str,*,http=None):
        if not api_key:raise ValueError('TranscriptFetch key required')
        self.key=api_key
        self.http=http

    def _send(self,method:str,path:str,**kwargs)->dict:
        import httpx
        if not path.startswith('/api/v2/transcripts/') or '://' in path:
            raise TranscriptFetchError('Unexpected transcript endpoint')
        headers={'Authorization':'Bearer '+self.key,
                 'Content-Type':'application/json',
                 'Accept':'application/json'}
        try:
            client=self.http or httpx
            response=getattr(client,method)(BASE+path,headers=headers,timeout=58,**kwargs)
            response.raise_for_status()
            payload=response.json()
            if not isinstance(payload,dict):
                raise TranscriptFetchError('Malformed provider response')
            return payload
        except TranscriptFetchError:raise
        except Exception as exc:
            raise TranscriptFetchError('TranscriptFetch request failed ('+type(exc).__name__+')') from None

    def _result(self,url:str,payload:dict)->dict:
        if payload.get('ok') is not True:
            raise TranscriptFetchError('TranscriptFetch returned failure')
        if payload.get('status')=='processing':
            job_id=validate_poll_id(payload.get('job_id'))
            polled=payload.get('poll_url')
            if polled is not None and polled!='/api/v2/transcripts/jobs/'+job_id:
                raise TranscriptFetchError('Provider poll URL does not match job')
            return {'state':'processing','job_id':job_id}
        return {'state':'completed','transcript':normalize_transcriptfetch(url,payload)}

    def start(self,url:str)->dict:
        canonical=canonicalize_instagram(url)
        return self._result(canonical,self._send('post','/api/v2/transcripts/video',
              json={'video':canonical,'mode':'audio','timestamps':True}))

    def poll(self,url:str,job_id:str)->dict:
        canonical=canonicalize_instagram(url)
        jid=validate_poll_id(job_id)
        return self._result(canonical,self._send('get','/api/v2/transcripts/jobs/'+jid))
