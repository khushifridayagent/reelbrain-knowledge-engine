"""Bounded public-only research. No arbitrary URL fetch from model output."""
import os,re,ipaddress,json,base64,socket,ssl,http.client,time,threading
from collections import deque,OrderedDict
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urlsplit,quote
import httpx

def safe_public_url(u):
    try:
        p=urlsplit(u);h=p.hostname or ''
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or not h or '.' not in h or h.endswith(('.local','.internal','.localhost','.test','.invalid')) or h=='localhost':return False
        try:return ipaddress.ip_address(h).is_global
        except ValueError:return bool(re.fullmatch(r'[a-zA-Z0-9.-]+',h))
    except ValueError:return False

def github_repo(u):
    if not safe_public_url(u):return None
    p=urlsplit(u)
    if p.hostname!='github.com':return None
    x=p.path.strip('/').split('/')
    if len(x)<2 or x[0] in ('topics','search','orgs','settings','login','features') or not all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',s) for s in x[:2]):return None
    return x[0],x[1].removesuffix('.git')

def public_research_query(q):
    q=q.strip()
    if not 2<=len(q)<=220 or re.search(r'https?://|\b(?:sk-|ghp_|github_pat_|AIza|bearer\s|password\s*=|token\s*=)',q,re.I) or '@' in q:raise ValueError('Use public tool or repository names, not URLs, private notes, or credentials.')
    return q

class _PageText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.skip=0;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','noscript','svg','template'):self.skip+=1
        elif tag in ('p','li','h1','h2','h3','h4','pre','br','tr'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','svg','template'):self.skip=max(0,self.skip-1)
        elif tag in ('p','li','pre','tr'):self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip:self.parts.append(data)

class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):super().__init__(host,port=443,timeout=6,context=ssl.create_default_context());self.ip=ip
    def connect(self):
        sock=socket.create_connection((self.ip,443),self.timeout)
        try:self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
        except Exception:sock.close();raise

def read_public_page(url):
    """Read a bounded public HTTPS document, pinned DNS, no redirects/cookies/keys."""
    if not safe_public_url(url):raise ValueError('Not a public URL')
    p=urlsplit(url)
    # Avoid sending search-result signed URLs, tracking values or secrets.
    if p.query or len(p.path)>1200:raise ValueError('Query URLs are not fetched')
    host=p.hostname
    ips=sorted({r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)})
    if not ips or not all(ipaddress.ip_address(ip).is_global for ip in ips):raise ValueError('Non-public DNS response')
    conn=_PinnedHTTPS(host,ips[0])
    try:
        conn.request('GET',p.path or '/',headers={'User-Agent':'ReelBrainStudio/0.1 (public documentation retrieval)','Accept':'text/html,text/plain,text/markdown','Accept-Encoding':'identity'})
        r=conn.getresponse()
        if r.status!=200 or r.getheader('Content-Encoding','identity') not in ('identity',''):raise ValueError('Unavailable public page')
        typ=r.getheader('Content-Type','').lower()
        if not any(typ.startswith(x) for x in ('text/html','text/plain','text/markdown')):raise ValueError('Unsupported document type')
        raw=r.read(256001);text=raw[:256000].decode('utf-8','replace')
        if typ.startswith('text/html'):
            parser=_PageText();parser.feed(text);text=' '.join(''.join(parser.parts).split())
        return text[:8000]
    finally:conn.close()

class Research:
    def __init__(self,client=None,planner=None):
        self.planner=planner
        self.http=client or httpx.Client(timeout=httpx.Timeout(30,connect=5),follow_redirects=False,trust_env=False)
        self.lock=threading.RLock();self.cache=OrderedDict();self.usage={'search':deque(),'fetch':deque()};self.blocked={}
    def _tiny(self,kind,key,*,query=None,urls=()):
        # Local sliding-window safeguards. Provider 429 is authoritative across instances.
        # No paid API, browser automation, private URLs, or caller-controlled endpoint.
        limits=[(60,30),(3600,500)] if kind=='search' else [(60,150),(86400,1000)]
        cost=1 if kind=='search' else len(urls)
        ident=(kind,query if kind=='search' else tuple(urls));now=time.monotonic()
        with self.lock:
            entry=self.cache.get(ident)
            if entry and entry[0]>now:return entry[1]
            q=self.usage[kind]
            while q and q[0][0]<now-limits[-1][0]:q.popleft()
            if self.blocked.get(kind,0)>now or any(sum(n for t,n in q if t>now-seconds)+cost>lim for seconds,lim in limits):raise RuntimeError('TinyFish rate budget temporarily unavailable')
            q.append((now,cost))
        headers={'X-API-Key':key,'Accept':'application/json'}
        for attempt in range(2):
            try:
                if kind=='search':r=self.http.get('https://api.search.tinyfish.ai',params={'query':query},headers=headers)
                else:r=self.http.post('https://api.fetch.tinyfish.ai',json={'urls':list(urls),'format':'markdown','ttl':900,'per_url_timeout_ms':18000},headers=headers)
                if r.status_code in (401,402,403,429):
                    try:delay=max(1,min(3600,int(r.headers.get('retry-after','60'))))
                    except ValueError:delay=60
                    with self.lock:self.blocked[kind]=time.monotonic()+(delay if r.status_code==429 else 300)
                    raise RuntimeError('TinyFish provider unavailable HTTP '+str(r.status_code))
                r.raise_for_status();data=r.json()
                if not isinstance(data,dict) or not isinstance(data.get('results'),list):raise ValueError('Malformed TinyFish result')
                # Do not cache empty/failed fetch results; preserve ability to retry.
                if data['results'] and not data.get('errors'):
                    with self.lock:
                        self.cache[ident]=(time.monotonic()+900,data)
                        while len(self.cache)>256:self.cache.popitem(last=False)
                return data
            except (httpx.TransportError,httpx.HTTPStatusError):
                if attempt:raise
                # Retried calls count too; stop if local capacity is exhausted.
                with self.lock:
                    now=time.monotonic();q=self.usage[kind]
                    if any(sum(n for t,n in q if t>now-seconds)+cost>lim for seconds,lim in limits):raise RuntimeError('TinyFish rate budget temporarily unavailable')
                    q.append((now,cost))
                time.sleep(.35*(2**attempt))
    def _web(self,query,key,docs,warnings):
        terms=query.casefold().split();broad=any(x in terms for x in ('compare','versus','pricing','limitations','workflow','automation','implementation','features'))
        queries=list(dict.fromkeys([query,query+' official documentation',query+' pricing limitations'] if broad else [query,query+' official documentation']))
        if self.planner:
            try:queries=list(dict.fromkeys([query]+self.planner(query)))[:4]
            except (RuntimeError,ValueError,TypeError):pass
        seen={};fetched=set();attempts=0;pages=0
        def search(q):
            try:return self._tiny('search',key,query=public_research_query(q))['results']
            except (RuntimeError,httpx.HTTPError,ValueError,KeyError):return None
        with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(search,queries))
        def add(rows):
            for row in rows or []:
                if not isinstance(row,dict):continue
                url=row.get('url','')
                if isinstance(url,str) and not url.startswith(('http://','https://')):url='https://'+url
                if not safe_public_url(url):continue
                p=urlsplit(url)
                if p.query or len(p.path)>1200 or p.hostname in ('instagram.com','www.instagram.com'):continue
                url=p._replace(fragment='').geturl()
                if url in seen:continue
                title=str(row.get('title',''))[:180];snippet=str(row.get('snippet',''))[:2400]
                priority=(2 if p.hostname.startswith(('docs.','developer.','developers.')) or 'official' in title.lower() else 0)+(1 if github_repo(url) else 0)
                seen[url]=(priority,title,snippet)
        for rows in results:
            if rows is None:warnings.append('TinySearch request unavailable or quota limited.')
            else:attempts+=1;add(rows)
        def fetch_more(limit):
            nonlocal pages
            ranked=sorted((u for u in seen if u not in fetched),key=lambda u:-seen[u][0])[:limit]
            if not ranked:return
            fetched.update(ranked)
            try:
                payload=self._tiny('fetch',key,urls=ranked)
                successes=set()
                for row in payload['results']:
                    if not isinstance(row,dict) or row.get('url') not in ranked or row.get('url') in successes:continue
                    final=row.get('final_url') or row['url'];body=row.get('text')
                    if not safe_public_url(final) or not isinstance(body,str) or not body.strip():continue
                    successes.add(row['url']);pages+=1
                    docs.append({'url':final,'title':str(row.get('title') or seen[row['url']][1])[:180],'text':body[:10000],'kind':'web_page_excerpt'})
                if set(ranked)-successes:warnings.append('Some TinyFetch pages unavailable; snippets are not page verification.')
            except (RuntimeError,httpx.HTTPError,ValueError,KeyError):warnings.append('TinyFetch unavailable or quota limited.')
        fetch_more(6 if broad else 4)
        if pages<2 and attempts and len(query)<170:
            add(search(query+' official setup guide'));fetch_more(4)
        # Unfetched snippets are explicitly weaker than retrieved content.
        if pages<2:
            for u,(_,title,snippet) in list(seen.items())[:3]:
                if snippet:docs.append({'url':u,'title':title,'text':snippet,'kind':'web_search_excerpt'})
        if not pages:warnings.append('No actual webpage content retrieved.')
        elif len({urlsplit(d['url']).hostname for d in docs if d['kind']=='web_page_excerpt'})<2:warnings.append('Limited independent web sources; cross-source confirmation may be incomplete.')

    def run(self,query,urls=()):
        query=public_research_query(query);docs=[];warnings=[];repos=[]
        def request(url,headers=None,params=None):
            r=self.http.get(url,headers=headers,params=params);r.raise_for_status();return r.json()
        headers={'Accept':'application/vnd.github+json','User-Agent':'ReelBrain-Knowledge-Studio'}
        token=os.getenv('GH_CHATBOT_TOKEN');
        if token:headers['Authorization']='Bearer '+token
        for u in urls:
            if pair:=github_repo(u):repos.append(pair)
        if not repos:
            try:
                j=request('https://api.github.com/search/repositories',headers,{'q':query+' in:name,description','per_page':3})
                repos.extend(tuple(r['full_name'].split('/')) for r in j.get('items',[]) if not r.get('private') and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',r.get('full_name','')))
            except (httpx.HTTPError,ValueError,KeyError):warnings.append('GitHub search unavailable or rate limited.')
        for owner,repo in list(dict.fromkeys(repos))[:3]:
            if not all(re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',x) for x in (owner,repo)):continue
            base='https://api.github.com/repos/'+quote(owner,safe='')+'/'+quote(repo,safe='');source=f'https://github.com/{owner}/{repo}'
            try:
                meta=request(base,headers)
                if meta.get('private') or meta.get('full_name','').lower()!=f'{owner}/{repo}'.lower():continue
                details={k:meta.get(k) for k in ('full_name','description','archived','updated_at','pushed_at','language','stargazers_count','open_issues_count','license','default_branch')}
                docs.append({'url':source,'title':f'{owner}/{repo} — repository metadata','text':json.dumps(details,ensure_ascii=False)[:4000],'kind':'github_metadata'})
                rd=request(base+'/readme',headers)
                if rd.get('encoding')=='base64' and len(rd.get('content',''))<=200000:
                    body=base64.b64decode(rd['content']).decode('utf-8','replace')[:12000]
                    docs.append({'url':rd.get('html_url') if safe_public_url(rd.get('html_url','')) else source,'title':f'{owner}/{repo} README','text':body,'kind':'github_readme'})
            except (httpx.HTTPError,ValueError,KeyError):warnings.append(f'Public repository documentation unavailable: {owner}/{repo}.')
        key=os.getenv('TINYFISH_CHATBOT_API_KEY')
        if key and os.getenv('STUDIO_WEB_SEARCH_APPROVED')=='1':self._web(query,key,docs,warnings)
        else:warnings.append('General web search disabled; GitHub-only verification.')
        return {'documents':docs,'warnings':list(dict.fromkeys(warnings))}
