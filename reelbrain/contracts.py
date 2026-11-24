"""Strict evidence-to-claim contracts; model output is always considered untrusted."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import re
from urllib.parse import urlsplit,urlunsplit

URL_PATTERN = re.compile(r'(?<![\w@])(?:https?://)?(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}/[^\s<>"\x27)\]}]+',re.I)
_ALLOWED = re.compile(r'^[A-Za-z0-9._~!$&()*+,;=:@%/-]+$')

@dataclass(frozen=True)
class Observation:
    text:str
    kind:str='document'
    locator:str=''
    confidence:float|None=None
    @property
    def uid(self)->str:
        return hashlib.sha256((self.kind+'\x00'+self.locator+'\x00'+self.text).encode()).hexdigest()[:28]

@dataclass(frozen=True)
class ResourceCandidate:
    name:str
    url:str
    purpose:str=''
    claimed_features:tuple[str,...]=()

@dataclass(frozen=True)
class AcceptedResource:
    name:str
    url:str
    purpose:str
    evidence_ids:tuple[str,...]

@dataclass(frozen=True)
class RejectedResource:
    name:str
    url:str
    reason:str

@dataclass
class FilterResult:
    accepted:list[AcceptedResource]=field(default_factory=list)
    rejected:list[RejectedResource]=field(default_factory=list)

def canonical_resource(url:str)->str:
    url=url.strip().rstrip('.,;!?:')
    if url.lower().startswith('github.com/'):
        url='https://'+url
    parts=urlsplit(url)
    host=(parts.hostname or '').lower()
    if parts.scheme not in ('https','http') or not host or parts.username or parts.password or (parts.port not in (None,80,443)):
        raise ValueError('unsupported URL format')
    if host in ('localhost','127.0.0.1') or host.endswith('.local') or not re.fullmatch(r'[a-z0-9.-]+',host) or '.' not in host:
        raise ValueError('unsafe hostname')
    if not _ALLOWED.fullmatch(parts.path) or '\\' in url:
        raise ValueError('unsafe path')
    path=parts.path.rstrip('/')
    if host in ('github.com','www.github.com'):
        seg=path.split('/')
        if len(seg)<3 or not seg[1] or not seg[2]: raise ValueError('incomplete GitHub identity')
        host='github.com'
        path='/'+seg[1]+'/'+seg[2].removesuffix('.git')
    return urlunsplit(('https',host,path,'',''))

def candidate_urls(text:str)->list[ResourceCandidate]:
    result=[];seen=set()
    for match in URL_PATTERN.finditer(text):
        raw=match.group(0).rstrip('.,;!?')
        try: normalized=canonical_resource(raw)
        except (ValueError,TypeError):continue
        if normalized not in seen:
            seen.add(normalized)
            parts=urlsplit(normalized)
            name=parts.path.strip('/').split('/')[-1] or parts.hostname
            result.append(ResourceCandidate(name=name,url=normalized,purpose=text[:300]))
    return result

def evidence_filter(candidates:list[ResourceCandidate], observations:list[Observation])->FilterResult:
    """Linear-time, evidence-backed resource filtering for large reports.

    Each input observation is scanned *once* and its supported URLs indexed.
    Even exact duplicate links remain traceable to each source observation UID;
    generating model output can never provide independent URL evidence.
    """
    out=FilterResult()
    proofs:dict[str,list[str]]={}
    allowed={'ocr','qr','asr','caption','document','manual','verified_doc'}
    for ev in observations:
        if ev.kind not in allowed:
            continue
        ev_urls=set()
        for found in URL_PATTERN.finditer(ev.text):
            try:
                normalized=canonical_resource(found.group(0))
            except (ValueError,TypeError):
                continue
            # Each observation contributes at most one citation for the URL.
            if normalized in ev_urls:
                continue
            ev_urls.add(normalized)
            proofs.setdefault(normalized,[]).append(ev.uid)

    for candidate in candidates:
        try:
            url=canonical_resource(candidate.url)
        except (ValueError,TypeError):
            out.rejected.append(RejectedResource(candidate.name,candidate.url,'invalid_url'))
            continue
        supporting_ids=proofs.get(url,[])
        if supporting_ids:
            out.accepted.append(AcceptedResource(candidate.name,url,candidate.purpose,
                                                 tuple(dict.fromkeys(supporting_ids))))
        else:
            out.rejected.append(RejectedResource(candidate.name,url,'unsupported_url'))
    return out
