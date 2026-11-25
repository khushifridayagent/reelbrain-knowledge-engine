import os,hmac,re,threading,time
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,HTTPException,Header,Response
from pydantic import BaseModel,Field
from .core import SearchIndex,LocalModels,canonical_instagram
from .db import Database,filter_args
from .llm import LLM
from .research import Research,public_research_query,github_repo

class SearchBody(BaseModel):
    question:str=Field(min_length=2,max_length=1000)
    filters:dict[str,str]=Field(default_factory=dict)
    mode:Literal['auto','search','all','count']='auto'
    offset:int=Field(default=0,ge=0,le=1000000)
    limit:int=Field(default=8,ge=1,le=20)
class DetailBody(BaseModel):
    question:str=Field(min_length=2,max_length=1000)
    sources:list[str]=Field(min_length=1,max_length=8)
    search_context:str=Field(default='',max_length=1000)
    history:list[str]=Field(default_factory=list,max_length=3)
    public_query:str=Field(default='',max_length=220)
    research:bool=False
class SubmitBody(BaseModel):
    url:str=Field(min_length=10,max_length=2048)

class Services:
    def __init__(self):
        self.db=None;self.index=None;self.llm=LLM();self.research=Research(planner=self.llm.public_plan);self.lock=threading.Lock();self.last=0;self.sync_state={}
    def open(self):
        if self.db is None:
            dsn=os.getenv('STUDIO_DB_URL','')
            if not dsn:raise RuntimeError('Studio database access is not configured.')
            # Only connect to the expected project with a dedicated Studio role.
            from urllib.parse import urlsplit
            u=urlsplit(dsn);host=u.hostname or '';user=u.username or ''
            if not (host=='db.xlkdzrhzizuftbnitodr.supabase.co' or (host.endswith('.pooler.supabase.com') and user=='reelbrain_studio_app.xlkdzrhzizuftbnitodr')):raise RuntimeError('Wrong database project.')
            if user not in ('reelbrain_studio_app','reelbrain_studio_app.xlkdzrhzizuftbnitodr'):raise RuntimeError('Dedicated Studio credential required; never use postgres/service_role.')
            self.db=Database(dsn,ca_cert=os.getenv('STUDIO_DB_CA_CERT',''))
        if self.index is None:
            path=Path(os.getenv('STUDIO_INDEX_PATH','./data/index.sqlite'));path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            self.index=SearchIndex(path,LocalModels())
    def refresh(self):
        with self.lock:
            self.open()
            if time.monotonic()-self.last>30 or not self.sync_state:
                self.sync_state=self.db.refresh(self.index);self.last=time.monotonic()
            return self.sync_state


def create_app(services=None):
    s=services or Services();app=FastAPI(title='ReelBrain Knowledge Studio',docs_url=None,redoc_url=None,openapi_url=None)
    def authorize(authorization:str|None=Header(default=None)):
        secret=os.getenv('STUDIO_BACKEND_TOKEN','')
        if len(secret)<32:raise HTTPException(503,'Studio access not configured')
        if not authorization or not hmac.compare_digest(authorization,'Bearer '+secret):raise HTTPException(401,'Unauthorized')
    @app.middleware('http')
    async def security(request,call_next):
        response=await call_next(request);response.headers['Cache-Control']='no-store';response.headers['X-Content-Type-Options']='nosniff';return response
    def ready():
        try:return s.refresh()
        except Exception:raise HTTPException(503,'Private index unavailable. Check Studio credentials and model runtime.') from None
    @app.get('/health')
    def health():return {'status':'ok'}
    @app.post('/search',dependencies=[Depends(authorize)])
    def search(body:SearchBody):
        try:f=filter_args(body.filters)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        q=body.question.strip()
        if body.mode=='count':
            try:
                with s.lock:s.open()
                return {'mode':'count','counts':s.db.stats(f),'sources':[]}
            except Exception:raise HTTPException(503,'Private count query unavailable') from None
        sync=ready();queries,intent=s.llm.plan(q);mode=body.mode if body.mode!='auto' else intent
        if mode=='count' and body.mode=='auto' and not f.get('tool'):
            # Count questions on an explicit saved corpus or metadata filter only;
            # topic-specific counts use the enumerated retrieval path.
            if re.fullmatch(r'(?i)(how many|count|total|kitne|कितने)?\s*(saved\s+)?(reels|posts|items|sources|jobs|रील्स|रील)\s*(saved|are there|हैं)?[? ]*',q) or f.get('creator') or f.get('date_from') or f.get('date_to'):
                return {'mode':'count','counts':s.db.stats(f),'sync':sync,'sources':[]}
            mode='all'
        if mode=='count':return {'mode':'count','counts':s.db.stats(f),'sync':sync,'sources':[]}
        if mode=='all':
            x=s.index.search(q,queries,f,min(body.limit,20),enumerate_all=True,offset=body.offset);cards=x['results'];answer=s.llm.map_reduce(q,cards) if cards else None
            return {'mode':'all','sources':cards,'answer':answer,'queries':queries,'total_keyword_matches':x['total_keyword_matches'],'next_offset':x['next_offset'],'sync':sync,'note':'Keyword enumeration; semantic matches are not guaranteed exhaustive. Summary covers this page.'}
        cards=s.index.search(q,queries,f,min(body.limit,8));answer=s.llm.summarize(q,cards) if cards else None
        return {'mode':'search','sources':cards,'answer':answer,'queries':queries,'sync':sync,'note':'Source evidence is available even when LLM synthesis is disabled or unavailable.'}
    @app.post('/detail',dependencies=[Depends(authorize)])
    def detail(body:DetailBody):
        ready()
        try:urls=list(dict.fromkeys(canonical_instagram(x) for x in body.sources))
        except ValueError:raise HTTPException(422,'Invalid selected source') from None
        context='\n'.join([body.search_context,*[h[:500] for h in body.history],body.question])[:2500]
        queries,_=s.llm.plan(context[:1000])
        cards=s.index.contextual_sources(context,queries,urls)
        if not cards:raise HTTPException(404,'Selected source is not indexed')
        # Retrieve question-relevant evidence only within selected sources, rather than unrelated DB records.
        # Exact source IDs are validated against private index; external search never receives raw private text.
        ext={'documents':[],'warnings':[]}
        if body.research:
            try:query=public_research_query(body.public_query)
            except ValueError as e:raise HTTPException(422,str(e)) from None
            links=[]
            for c in cards:
                for e in c['evidence']:
                    links.extend(u.rstrip('.,);') for u in re.findall(r'https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',e['text']) if github_repo(u))
            ext=s.research.run(query,links)
        answer=s.llm.summarize(context,cards,ext['documents'],detail=True)
        return {'sources':cards,'answer':answer,'public_sources':ext['documents'],'warnings':ext['warnings'],'note':'Public research is independent of saved Reel evidence. Review source links; no code execution was performed.'}
    @app.post('/submit',dependencies=[Depends(authorize)])
    def submit(body:SubmitBody):
        try:url=canonical_instagram(body.url)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        try:
            with s.lock:s.open()
            result=s.db.submit(url);return result
        except Exception:raise HTTPException(503,'Submission unavailable. Existing pipeline has not been modified.') from None
    @app.post('/counts',dependencies=[Depends(authorize)])
    def counts(body:SearchBody):
        try:f=filter_args(body.filters)
        except ValueError as e:raise HTTPException(422,str(e)) from None
        try:
            with s.lock:s.open()
            return s.db.stats(f)
        except Exception:raise HTTPException(503,'Private count query unavailable') from None
    return app
app=create_app()
