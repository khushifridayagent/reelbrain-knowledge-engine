"""Pure, read-only parser for signed Instagram *one-to-one* DM webhook events.

This does not access group chats, authenticate users, collect content or scrape.
Only source links and hashed identifiers should enter persistent work queues.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,re
from urllib.parse import urlsplit

_URL=re.compile(r'https?://[^\s<>"\']+',re.I)
_ID=re.compile(r'^[a-zA-Z0-9_-]{4,160}$')
_ALLOWED_TYPES={'ig_reel','reel','ig_post','post','share'}

@dataclass(frozen=True)
class DMShare:
    source_url:str
    provider_event_id:str
    sender_digest:str

def instagram_url(raw:str)->str|None:
    if not isinstance(raw,str) or len(raw)>2048:return None
    try:p=urlsplit(raw.strip().rstrip('.,;!)]}'))
    except ValueError:return None
    if p.scheme!='https' or p.username or p.password or p.port or p.hostname not in {'instagram.com','www.instagram.com'}:
        return None
    chunks=p.path.strip('/').split('/')
    if len(chunks)<2 or chunks[0] not in {'reel','p','tv'} or not _ID.fullmatch(chunks[1]):return None
    return f'https://www.instagram.com/{chunks[0]}/{chunks[1]}/'

def links_from_event(event:dict)->list[str]:
    message=event.get('message') or {}
    if not isinstance(message,dict):return []
    texts=[]
    if isinstance(message.get('text'),str):texts.append(message['text'][:10000])
    attachments=message.get('attachments',[])
    if isinstance(attachments,list):
        for a in attachments[:20]:
            if not isinstance(a,dict) or a.get('type') not in _ALLOWED_TYPES:continue
            p=a.get('payload')
            if isinstance(p,dict):
                for k in ('url','permalink'):
                    if isinstance(p.get(k),str):texts.append(p[k])
    seen=set();links=[]
    for t in texts:
        for match in _URL.finditer(t):
            link=instagram_url(match.group(0))
            if link and link not in seen: seen.add(link);links.append(link)
    return links[:12]

def collect_dm_shares(payload:dict,receiver_id:str,allowed_senders:set[str])->list[DMShare]:
    if not isinstance(payload,dict) or payload.get('object')!='instagram' or not receiver_id or not allowed_senders:return []
    rows={}
    entries=payload.get('entry')
    if not isinstance(entries,list):return []
    for entry in entries[:40]:
        if not isinstance(entry,dict):continue
        events=entry.get('messaging',[])
        if not isinstance(events,list):continue
        for ev in events[:100]:
            if not isinstance(ev,dict):continue
            sender=ev.get('sender') or {};receiver=ev.get('recipient') or {};message=ev.get('message') or {}
            if not isinstance(sender,dict) or not isinstance(receiver,dict) or not isinstance(message,dict):continue
            sid=sender.get('id');rid=receiver.get('id');mid=message.get('mid')
            if not isinstance(sid,str) or sid not in allowed_senders or rid!=receiver_id:continue
            if not isinstance(mid,str) or not mid or len(mid)>256 or message.get('is_echo') or message.get('is_deleted'):continue
            if ev.get('thread') or ev.get('participants'):continue  # unsupported group metadata
            for url in links_from_event(ev):
                rows.setdefault(url,DMShare(url,hashlib.sha256(mid.encode()).hexdigest(),hashlib.sha256(sid.encode()).hexdigest()))
    return list(rows.values())
