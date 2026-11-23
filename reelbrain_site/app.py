"""Minimal authenticated website. No Supabase credentials enter browser or logs.

Requires REELBRAIN_DB_URL and REELBRAIN_DASHBOARD_TOKEN. Uses dedicated Reelbrain
Postgres only. `/api/details` runs independent read-only research without saving.
"""
from __future__ import annotations
import hmac,os
from pathlib import Path
from fastapi import FastAPI,Header,HTTPException,Query,Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from reelbrain.online_research import summarize_repository,ResearchUnavailable
from reelbrain.instagram_dm import instagram_url

app=FastAPI(title='Reelbrain private search',docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def security(request:Request,call_next):
    res=await call_next(request)
    res.headers['Cache-Control']='no-store';res.headers['X-Content-Type-Options']='nosniff'
    res.headers['Referrer-Policy']='no-referrer';res.headers['X-Frame-Options']='DENY'
    res.headers['Content-Security-Policy']="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    return res

def authorize(token:str|None):
    key=os.getenv('REELBRAIN_DASHBOARD_TOKEN','')
    if len(key)<32:raise HTTPException(503,'Owner authentication has not been configured')
    if not token or not token.startswith('Bearer ') or not hmac.compare_digest(token[7:],key):raise HTTPException(401,'Owner access required')

def query_db(statement:str,params:tuple=()):
    url=os.getenv('REELBRAIN_DB_URL','')
    if not url:raise HTTPException(503,'Private database is not configured')
    try:import psycopg
    except ImportError:raise HTTPException(503,'psycopg is not installed')
    # DSN is a server environment secret; never sent to client.
    with psycopg.connect(url,connect_timeout=4,autocommit=True) as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute('SET statement_timeout = 5000')
            cur.execute(statement,params)
            return cur.fetchall() if cur.description else []

@app.get('/',response_class=HTMLResponse)
def index():return (Path(__file__).parent/'index.html').read_text('utf-8')

@app.get('/ui.css')
def ui_css():
    from fastapi.responses import Response
    return Response((Path(__file__).parent/'ui.css').read_text('utf-8'),media_type='text/css')

@app.get('/ui.js')
def ui_js():
    from fastapi.responses import Response
    return Response((Path(__file__).parent/'ui.js').read_text('utf-8'),media_type='text/javascript')

@app.get('/api/health')
def health():return {'service':'reelbrain_website','auth_enabled':len(os.getenv('REELBRAIN_DASHBOARD_TOKEN',''))>=32,
                     'source_processing':'separate_worker_required','instagram_groups_supported':False}

@app.get('/api/search')
def search(q:str=Query(min_length=2,max_length=180),limit:int=Query(default=20,ge=1,le=50),authorization:str|None=Header(default=None)):
    authorize(authorization)
    rows=query_db('''SELECT repo,repo_url,what_it_does,core_features,practical_use_cases,verification_level,source_locator,search_rank
       FROM reelbrain_research.search_catalog_indexed(%s,%s)
       UNION ALL
       SELECT repo,repo_url,what_it_does,core_features,practical_use_cases,verification_level,source_locator,search_rank
       FROM reelbrain_research.search_reels(%s,%s)
       ORDER BY search_rank DESC LIMIT %s''',(q,limit,q,limit,limit))
    return {'query':q,'results':rows,'evidence_notice':'Catalog features not independently verified unless status specifies otherwise.'}

class Link(BaseModel):
    url:str

@app.post('/api/intake',status_code=202)
def add_link(body:Link,authorization:str|None=Header(default=None)):
    authorize(authorization)
    canon=instagram_url(body.url)
    if canon is None:raise HTTPException(422,'Public Instagram /reel/ or /p/ URL required')
    rows=query_db('''INSERT INTO public.reelbrain_dm_jobs (source_url,inbound_event_id,sender_digest)
        VALUES (%s,%s,%s) ON CONFLICT(source_url) DO NOTHING
        RETURNING id,status,source_url''',(canon,'manual_website','0'*64))
    if not rows:
        rows=query_db('SELECT id,status,source_url FROM public.reelbrain_dm_jobs WHERE source_url=%s',(canon,))
    return {'job':rows[0],'note':'Saved durably. Media enrichment requires a connected, authorized worker.'}

@app.get('/api/details')
def details(url:str=Query(max_length=2048),authorization:str|None=Header(default=None)):
    authorize(authorization)
    try:return summarize_repository(url)
    except ResearchUnavailable as e:raise HTTPException(422,str(e))
