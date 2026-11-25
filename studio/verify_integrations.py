"""One-off synthetic integration checks. Never print payloads, tokens or private rows."""
import os, json, time, urllib.request, urllib.error, base64
from urllib.parse import urlencode, urlsplit
from concurrent.futures import ThreadPoolExecutor
def request(name,url,key=None,body=None,header='X-API-Key'):
    headers={'Accept':'application/json','User-Agent':'ReelBrain-Studio-Verification'}
    if key:headers[header]=key
    if body is not None:headers['Content-Type']='application/json'
    start=time.monotonic()
    try:
        with urllib.request.urlopen(urllib.request.Request(url,data=None if body is None else json.dumps(body).encode(),headers=headers),timeout=35) as r:
            data=json.load(r);print(name+' HTTP '+str(r.status)+' elapsed_ms='+str(round((time.monotonic()-start)*1000)),flush=True);return data
    except urllib.error.HTTPError as e:
        print(name+' HTTP '+str(e.code),flush=True);raise RuntimeError(name+' failed') from None
    except Exception:
        print(name+' transport_or_parse_failure',flush=True);raise RuntimeError(name+' failed') from None
def required(k):
    v=os.environ.get(k)
    if not v:raise RuntimeError(k+' missing')
    return v
def groq():
    key='Bearer '+required('GROQ_CHATBOT_API_KEY')
    models=request('groq_models','https://api.groq.com/openai/v1/models',key,header='Authorization')
    model='qwen/qwen3.8-27b'
    assert model in {x['id'] for x in models['data']}
    j=request('groq_generation','https://api.groq.com/openai/v1/chat/completions',key,{'model':model,'messages':[{'role':'user','content':'Return JSON object {"ok":true}. No other text.'}],'response_format':{'type':'json_object'},'max_completion_tokens':256},header='Authorization')
    assert json.loads(j['choices'][0]['message']['content']).get('ok') is True
def gemini():
    key=required('GEMINI_CHATBOT_API_KEY')
    model='gemini-3.5-flash-lite'
    request('gemini_model','https://generativelanguage.googleapis.com/v1beta/models/'+model,key,header='x-goog-api-key')
    j=request('gemini_generation','https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',key,{'contents':[{'parts':[{'text':'Return JSON object {"ok":true}.'}]}],'generationConfig':{'responseMimeType':'application/json','maxOutputTokens':256}},header='x-goog-api-key')
    assert json.loads(''.join(p.get('text','') for p in j['candidates'][0]['content']['parts'])).get('ok') is True
def github():
    key='Bearer '+required('GH_CHATBOT_TOKEN')
    j=request('github_repo','https://api.github.com/repos/fastapi/fastapi',key,header='Authorization')
    assert j['full_name']=='fastapi/fastapi' and not j['private']
    j=request('github_readme','https://api.github.com/repos/fastapi/fastapi/readme',key,header='Authorization')
    assert b'FastAPI' in base64.b64decode(j['content'])
def tinyfish():
    key=required('TINYFISH_CHATBOT_API_KEY')
    j=request('tinysearch','https://api.search.tinyfish.ai?'+urlencode({'query':'FastAPI official documentation features','include_domains':'fastapi.tiangolo.com'}),key)
    hits=[x for x in j.get('results',[]) if isinstance(x.get('url'),str) and urlsplit(x['url']).hostname=='fastapi.tiangolo.com']
    assert hits
    url=hits[0]['url']
    if not url.startswith('https://') or urlsplit(url).query:url='https://fastapi.tiangolo.com/'
    j=request('tinyfetch','https://api.fetch.tinyfish.ai',key,{'urls':[url],'format':'markdown','per_url_timeout_ms':25000})
    assert any(x.get('url')==url and isinstance(x.get('text'),str) and 'fastapi' in x['text'].lower() and len(x['text'])>100 for x in j.get('results',[]))
    print('tinyfetch_verified_pages=1 search_requests=1 fetch_urls=1',flush=True)
def database():
    import psycopg
    dsn=required('REELBRAIN_DB_URL')
    u=urlsplit(dsn)
    assert (u.hostname=='db.xlkdzrhzizuftbnitodr.supabase.co' or (u.hostname and u.hostname.endswith('.pooler.supabase.com') and 'xlkdzrhzizuftbnitodr' in (u.username or '')))
    with psycopg.connect(dsn,connect_timeout=8,options='-c statement_timeout=10000') as con:
        con.execute('set transaction read only')
        assert con.execute('select count(*) from public.reelbrain_reel_knowledge').fetchone()[0]>=0
        con.rollback()
    print('database_read_only_pass',flush=True)
if __name__=='__main__':
    failed=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(fn):fn.__name__ for fn in (groq,gemini,github,tinyfish,database)}
        for f,name in futures.items():
            try:f.result();print(name+' PASS',flush=True)
            except Exception:failed.append(name);print(name+' FAIL',flush=True)
    if failed:raise SystemExit(1)
