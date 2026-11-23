"""Opt-in Meta Instagram professional account 1-to-1 messaging webhook.

Meta's official Instagram messaging API does NOT support existing DM group chats.
This adapter accepts only signed 1-to-1 shares from an explicit sender allowlist.
It saves *links only* and does not scrape Instagram, read other DMs, or reply.
"""
from __future__ import annotations
import hashlib, hmac, json, secrets
from datetime import datetime,timezone
from pathlib import Path
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import Response
from .store import KnowledgeStore
from .pipeline import KnowledgePipeline
from .sources import extract_instagram_urls


def create_meta_router(*,db_path:str|Path,tenant:str,app_secret:str|None=None,
                       verify_token:str|None=None,receiver_id:str|None=None,
                       allowed_senders:set[str]|None=None)->APIRouter:
    enabled=any((app_secret,verify_token,receiver_id,allowed_senders))
    if enabled and not all((app_secret,verify_token,receiver_id,allowed_senders)):
        raise ValueError('Meta requires app secret, verification token, professional account ID, sender allowlist')
    router=APIRouter(prefix='/webhooks/instagram')

    @router.get('')
    def verify(request:Request):
        if not enabled:raise HTTPException(503,'Meta integration not configured')
        qp=request.query_params
        if (qp.get('hub.mode')!='subscribe' or not secrets.compare_digest(qp.get('hub.verify_token',''),verify_token)
                or not qp.get('hub.challenge','').isdigit()):
            raise HTTPException(403,'Webhook token verification failed')
        return Response(qp['hub.challenge'],media_type='text/plain')

    @router.post('')
    async def receive(request:Request):
        if not enabled:raise HTTPException(503,'Meta integration not configured')
        body=await request.body()
        if len(body)>1024*1024:raise HTTPException(413,'Webhook payload too large')
        got=request.headers.get('X-Hub-Signature-256','')
        expected='sha256='+hmac.new(app_secret.encode(),body,hashlib.sha256).hexdigest()
        if not secrets.compare_digest(got,expected):
            raise HTTPException(403,'Invalid webhook signature')
        try:payload=json.loads(body)
        except ValueError:raise HTTPException(400,'Invalid JSON payload')
        if not isinstance(payload,dict) or payload.get('object')!='instagram':
            return {'accepted':False,'saved_links':0,'group_support':False}
        saved=0;scanned=0
        db=KnowledgeStore(db_path)
        try:
            db.con.execute('''CREATE TABLE IF NOT EXISTS meta_received_messages(
              tenant TEXT NOT NULL,hashed_sender TEXT NOT NULL,message_id TEXT NOT NULL,
              received_at TEXT NOT NULL,PRIMARY KEY(tenant,hashed_sender,message_id))''')
            entries=payload.get('entry',[])
            if not isinstance(entries,list):return {'accepted':False,'saved_links':0,'group_support':False}
            for entry in entries[:25]:
                if not isinstance(entry,dict) or str(entry.get('id',''))!=receiver_id:continue
                events=entry.get('messaging',[])
                if not isinstance(events,list):continue
                for event in events[:40]:
                    if not isinstance(event,dict):continue
                    sender=event.get('sender') or {};recipient=event.get('recipient') or {}
                    if not isinstance(sender,dict) or not isinstance(recipient,dict):continue
                    sid=str(sender.get('id',''))
                    if sid not in allowed_senders or str(recipient.get('id',''))!=receiver_id:continue
                    message=event.get('message') or {}
                    if not isinstance(message,dict) or message.get('is_echo') or message.get('is_deleted'):continue
                    mid=message.get('mid')
                    if not isinstance(mid,str) or not (1<=len(mid)<=180):continue
                    hashed_sender=hashlib.sha256(sid.encode()).hexdigest()
                    if db.con.execute('''SELECT 1 FROM meta_received_messages
                         WHERE tenant=? AND hashed_sender=? AND message_id=?''',(tenant,hashed_sender,mid)).fetchone():
                        continue
                    texts=[]
                    if isinstance(message.get('text'),str):texts.append(message['text'])
                    attachments=message.get('attachments') or []
                    if isinstance(attachments,list):
                        for a in attachments[:15]:
                            if not isinstance(a,dict) or a.get('type') not in ('ig_post','ig_reel','reel','post'):continue
                            p=a.get('payload') or {}
                            if isinstance(p,dict):
                                for key in ('url','permalink'):
                                    if isinstance(p.get(key),str):texts.append(p[key])
                    urls=extract_instagram_urls('\n'.join(texts)[:20000])[:10]
                    for url in urls:
                        result=KnowledgePipeline(db).ingest_url(url,tenant)
                        prior=db.con.execute('''SELECT 1 FROM jobs WHERE tenant=?
                             AND kind='await_permitted_media' AND idempotency_key=?''',(tenant,url)).fetchone()
                        db.enqueue(tenant,'await_permitted_media',
                                   {'canonical_url':url,'source_id':result['source_id']},url)
                        if prior is None:saved+=1
                    with db.transaction():
                        db.con.execute('INSERT OR IGNORE INTO meta_received_messages VALUES(?,?,?,?)',
                                       (tenant,hashed_sender,mid,datetime.now(timezone.utc).isoformat()))
                    scanned+=1
            return {'accepted':True,'saved_links':saved,'messages_checked':scanned,
                    'group_support':False,'media_extracted':False}
        finally:db.close()
    return router
