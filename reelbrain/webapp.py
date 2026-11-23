"""Private, opt-in intake + fast local search. NOT an Instagram group reader.

Only same-user authorized share, pasted links and owned media are supported.
No remote providers are contacted by this web application. Default listener is
127.0.0.1. HTTPS + explicit authentication required when externally deployed.
"""
from __future__ import annotations
from pathlib import Path
from typing import Annotated
import html, os, secrets, uuid, hashlib, json
from fastapi import FastAPI, HTTPException, Header, Form, Request, BackgroundTasks, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .store import KnowledgeStore
from .sources import canonicalize_instagram, extract_instagram_urls, InvalidSource
from .pipeline import KnowledgePipeline
from .fastsearch import FastCatalogSearch

_CSP="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
_STATIC=Path(__file__).resolve().parent/'static'

class LinkIntake(BaseModel):
    url:str=Field(min_length=12,max_length=2000)

class AppConfig:
    def __init__(self, db_path:str|Path, token:str, tenant:str='personal'):
        if not isinstance(token,str) or len(token)<24:
            raise ValueError('REELBRAIN_API_TOKEN must have 24+ characters')
        if not tenant or len(tenant)>50:raise ValueError('invalid tenant')
        self.db_path=Path(db_path)
        self.token=token
        self.tenant=tenant


def _page(incoming:str='')->str:
    # Static JavaScript uses meta contents; no HTML injection from OS share text.
    escaped=html.escape(incoming,quote=True)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0c1c36">
<meta name="incoming-url" content="{escaped}">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/app.css"><title>Reelbrain — personal research inbox</title></head>
<body><main><header><strong>REELBRAIN</strong><small>Private knowledge inbox · v0.7</small></header>
<section><h1>Save the Reel. Keep the knowledge.</h1><p>Paste an Instagram Reel/post link or share to this installed app. A link is saved immediately; its actual video content is not marked extracted until authorized media is processed.</p></section>
<section><label>Personal access token <input id="token" type="password" autocomplete="off" placeholder="Token from REELBRAIN_API_TOKEN"></label>
<label>Instagram link <input id="link" type="url" placeholder="https://www.instagram.com/reel/..."></label>
<button id="save">Save to private inbox</button><output id="status" role="status"></output></section>
<section><h2>Have the Reel file?</h2><p>Optional: upload only video or screenshots you own or are permitted to process. This starts local OCR; third-party AI services stay OFF.</p><label>Reel video / screenshot<input id="media-file" type="file" accept="video/mp4,video/webm,video/quicktime,image/png,image/jpeg,image/webp"></label><button id="upload">Upload authorized media</button><output id="upload-status" role="status"></output></section>
<section><label>Search your historical research <input id="query" type="search" placeholder="RAG, automation, OCR, GitHub..."></label>
<button id="search">Search knowledge</button><output id="results" role="status"></output></section>
<section><h2>Pending Reels</h2><button id="pending">Refresh queue</button><output id="pending-list"></output></section>
<footer>Media analysis requires permitted content. This app does not access Instagram DM groups or bypass login walls.</footer>
</main><script src="/app.js" defer></script></body></html>'''


def create_app(*,db_path:str|Path,token:str,tenant:str='personal',
               meta_app_secret:str|None=None,meta_verify_token:str|None=None,
               meta_receiver_id:str|None=None,meta_allowed_senders:set[str]|None=None)->FastAPI:
    cfg=AppConfig(db_path,token,tenant)
    app=FastAPI(title='Reelbrain personal inbox',version='0.7.0',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.cfg=cfg
    from .meta_webhook import create_meta_router
    app.include_router(create_meta_router(db_path=db_path,tenant=tenant,app_secret=meta_app_secret,
        verify_token=meta_verify_token,receiver_id=meta_receiver_id,allowed_senders=meta_allowed_senders))

    def authorize(authorization:str|None):
        if not authorization or not authorization.startswith('Bearer '):
            raise HTTPException(status_code=401,detail='Private API: bearer token required')
        got=authorization.removeprefix('Bearer ')
        if not secrets.compare_digest(got,cfg.token):
            raise HTTPException(status_code=401,detail='Invalid token')

    def open_store():
        return KnowledgeStore(cfg.db_path)

    @app.middleware('http')
    async def secure_headers(request:Request,call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']=_CSP
        response.headers['X-Frame-Options']='DENY'
        return response

    @app.get('/',response_class=HTMLResponse)
    def index():return _page()

    @app.post('/share',response_class=HTMLResponse)
    def receive_os_share(text:str=Form(default=''),title:str=Form(default=''),url:str=Form(default='')):
        # OS share data is untrusted. It is only prefilled in page for manual auth+submit.
        urls=extract_instagram_urls('\n'.join((text,title,url))[:10000])
        return _page(urls[0] if urls else '')

    @app.get('/manifest.webmanifest')
    def manifest():
        return JSONResponse({'name':'Reelbrain Knowledge Inbox','short_name':'Reelbrain',
                'display':'standalone','start_url':'/','scope':'/',
                'icons':[{'src':'/icon-192.png','sizes':'192x192','type':'image/png'},
                         {'src':'/icon-512.png','sizes':'512x512','type':'image/png'}],
                'background_color':'#0c1c36','theme_color':'#0c1c36',
                'share_target':{'action':'/share','method':'POST','enctype':'application/x-www-form-urlencoded',
                         'params':{'title':'title','text':'text','url':'url'}}})

    @app.get('/app.js')
    def js():return Response((_STATIC/'app.js').read_text(encoding='utf-8'),media_type='text/javascript')
    @app.get('/icon-{size}.png')
    def icon(size:int):
        if size not in (192,512):raise HTTPException(404,'not found')
        return Response((_STATIC/f'icon-{size}.png').read_bytes(),media_type='image/png')
    @app.get('/sw.js')
    def service_worker():
        return Response('self.addEventListener("install",()=>self.skipWaiting());self.addEventListener("activate",(event)=>event.waitUntil(self.clients.claim()));',media_type='text/javascript',headers={'Service-Worker-Allowed':'/'})

    @app.get('/app.css')
    def css():return Response((_STATIC/'app.css').read_text(encoding='utf-8'),media_type='text/css')

    @app.get('/api/health')
    def health():return {'status':'local_service_running','instagram_group_access':False,
                         'cloud_worker_attached':False,'model_calls':False}

    @app.post('/api/intake/link',status_code=202)
    def add_link(body:LinkIntake,authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        try:canon=canonicalize_instagram(body.url)
        except InvalidSource as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
        db=open_store()
        try:
            result=KnowledgePipeline(db).ingest_url(canon,cfg.tenant)
            jobid=db.enqueue(cfg.tenant,'await_permitted_media',{'canonical_url':canon,'source_id':result['source_id']},canon)
            return {'canonical_url':canon,'source_id':result['source_id'],
                    'status':'awaiting_authorized_media','job_id':jobid,'media_extracted':False,'external_calls':0}
        finally:db.close()

    @app.get('/api/search')
    def search(q:str='',limit:int=20,authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        if not 1<=limit<=50:raise HTTPException(422,'limit 1..50')
        db=open_store()
        try:
            hits=FastCatalogSearch(db).search(q,cfg.tenant,limit)
            return {'query':q,'hits':hits,'scope':'supplied historical research and README receipts',
                    'note':'catalog features are unverified unless shown otherwise','external_calls':0}
        finally:db.close()

    @app.get('/api/pending')
    def pending(authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        db=open_store()
        try:return {'items':db.pending_reels(cfg.tenant,100)}
        finally:db.close()

    @app.post('/api/intake/media',status_code=202)
    def intake_media(background_tasks:BackgroundTasks,
                     url:str=Form(...),file:UploadFile=File(...),
                     authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        from .media_inbox import MediaInbox,MediaInboxError
        inbox_dir=cfg.db_path.parent/'reelbrain_private_media'
        try:
            with MediaInbox(cfg.db_path,inbox_dir,cfg.tenant) as inbox:
                task=inbox.save_upload(file.file,file.filename or '',url)
        except MediaInboxError as exc:raise HTTPException(422,str(exc)) from exc
        if task['status']=='queued':
            def _process_one():
                with MediaInbox(cfg.db_path,inbox_dir,cfg.tenant) as worker:
                    worker.process_one(task['task_id'])
            background_tasks.add_task(_process_one)
        return {'task_id':task['task_id'],'status':task['status'],
                'url':task['source_url'],'note':'File stays private. Background processing runs only while this server runs.'}

    @app.get('/api/media-tasks/{task_id}')
    def media_task(task_id:str,authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        from .media_inbox import MediaInbox
        with MediaInbox(cfg.db_path,cfg.db_path.parent/'reelbrain_private_media',cfg.tenant) as inbox:
            task=inbox.get(task_id)
        if not task:raise HTTPException(404,'Task not found')
        return task

    @app.get('/api/media-tasks')
    def list_media_tasks(authorization:Annotated[str|None,Header()]=None):
        authorize(authorization)
        from .media_inbox import MediaInbox
        with MediaInbox(cfg.db_path,cfg.db_path.parent/'reelbrain_private_media',cfg.tenant) as inbox:
            return {'items':inbox.list_tasks()}

    return app
