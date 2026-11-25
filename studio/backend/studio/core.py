"""Private index. The production database is never mutated by retrieval."""
import json, re, sqlite3, threading, math
from dataclasses import dataclass, asdict
from urllib.parse import urlsplit
import numpy as np


def canonical_instagram(raw):
    try:
        u=urlsplit(raw.strip())
        if u.scheme!='https' or u.hostname not in ('instagram.com','www.instagram.com') or u.username or u.password or u.port not in (None,443): raise ValueError()
        m=re.fullmatch(r'/(reel|p|tv)/([A-Za-z0-9_-]{4,160})/?',u.path)
        if not m: raise ValueError()
        return f'https://www.instagram.com/{m[1]}/{m[2]}/'
    except (ValueError,AttributeError): raise ValueError('Paste a direct public Instagram Reel or post URL.') from None


def terms(text): return list(dict.fromkeys(re.findall(r'[^\W_]+(?:[-_.][^\W_]+)*',text.casefold(),re.UNICODE)))[:24]

def plan_queries(q):
    words=[w for w in terms(q) if w not in {'the','a','an','for','of','all','show','me','give','find','reels','posts','saved','about','please','मेरे','सभी','बताओ','दिखाओ'}]
    return list(dict.fromkeys(x for x in [q.strip(), ' '.join(words), ' '.join(words[:4]), ' '.join(words[-4:])] if x))[:4]

def reciprocal_rank(ranks):
    scores={}
    for rank in ranks:
        for i,key in enumerate(dict.fromkeys(rank),1): scores[key]=scores.get(key,0)+1/(60+i)
    return sorted(scores,key=lambda k:(-scores[k],k))

def cited_answer(obj, allowed):
    if not isinstance(obj,dict) or not isinstance(obj.get('answer'),str) or not obj['answer'].strip() or not isinstance(obj.get('citations'),list):return None
    refs=obj['citations']; inline=set(re.findall(r'\[([SW]\d+)\]',obj['answer']))
    if not refs or any(not isinstance(x,str) or x not in allowed for x in refs) or inline-set(refs) or not inline:return None
    return {'answer':obj['answer'][:18000],'citations':list(dict.fromkeys(refs))}

@dataclass(frozen=True)
class Document:
    id:str; source:str; creator:str; published:str; saved:str; status:str; kind:str; locator:str; text:str

class LocalModels:
    def __init__(self,embedding='intfloat/multilingual-e5-small',reranker='BAAI/bge-reranker-base'):
        self.name=embedding;self.reranker_name=reranker;self._embed=None;self._rerank=None;self.lock=threading.RLock()
    def embed(self,texts,query=False):
        from sentence_transformers import SentenceTransformer
        with self.lock:
            if self._embed is None:self._embed=SentenceTransformer(self.name,device='cpu',trust_remote_code=False)
            return self._embed.encode([('query: ' if query else 'passage: ')+t for t in texts],batch_size=24,normalize_embeddings=True,show_progress_bar=False)
    def rerank(self,query,docs):
        from sentence_transformers import CrossEncoder
        with self.lock:
            if self._rerank is None:self._rerank=CrossEncoder(self.reranker_name,device='cpu',trust_remote_code=False,max_length=512)
            return self._rerank.predict([(query,t) for t in docs],batch_size=8,show_progress_bar=False)

class SearchIndex:
    def __init__(self,path,models):
        self.models=models;self.lock=threading.RLock();self.con=sqlite3.connect(str(path),check_same_thread=False);self.con.row_factory=sqlite3.Row
        with self.con:
            self.con.execute('pragma journal_mode=WAL')
            self.con.executescript('''create table if not exists docs(id text primary key,source text,creator text,published text,saved text,status text,kind text,locator text,text text,vector blob);
              create index if not exists docs_source on docs(source); create index if not exists docs_saved on docs(saved);
              create virtual table if not exists lex using fts5(id UNINDEXED,text,tokenize='unicode61');
              create table if not exists versions(source text primary key,version text);
              create table if not exists settings(k text primary key,v text);''')
            row=self.con.execute("select v from settings where k='embedding'").fetchone()
            if row and row[0]!=models.name:raise RuntimeError('Embedding model changed: rebuild the separate Studio index.')
            self.con.execute("insert or ignore into settings values('embedding',?)",(models.name,))
    def version(self,source):
        with self.lock:
            r=self.con.execute('select version from versions where source=?',(source,)).fetchone();return r[0] if r else None
    def replace_source(self,source,docs,version):
        # compute outside transaction; failures leave previous snapshot intact
        vectors=[]
        for start in range(0,len(docs),64):vectors.extend(self.models.embed([d.text for d in docs[start:start+64]]))
        with self.lock,self.con:
            self.con.execute('delete from lex where id in (select id from docs where source=?)',(source,));self.con.execute('delete from docs where source=?',(source,))
            self.con.executemany('insert into docs values(?,?,?,?,?,?,?,?,?,?)',[(d.id,d.source,d.creator,d.published,d.saved,d.status,d.kind,d.locator,d.text,np.asarray(v,dtype='float32').tobytes()) for d,v in zip(docs,vectors)])
            self.con.executemany('insert into lex values(?,?)',[(d.id,d.text) for d in docs]);self.con.execute('insert into versions values(?,?) on conflict(source) do update set version=excluded.version',(source,version))
    def _filter(self,f):
        sql=[];args=[]
        for k,op,col in [('creator','=','creator'),('date_from','>=','saved'),('date_to','<=','saved'),('published_from','>=','published'),('published_to','<=','published'),('status','=','status')]:
            if f.get(k):
                sql.append('lower(d.creator)=lower(?)' if k=='creator' else f'd.{col} {op} ?');args.append(f[k])
        if f.get('_sources'):
            sql.append('d.source in ('+','.join('?' for _ in f['_sources'])+')');args.extend(f['_sources'])
        if f.get('tool'):
            sql.append("exists(select 1 from docs x where x.source=d.source and instr(lower(x.text),lower(?))>0)");args.append(f['tool'])
        return (' and '+' and '.join(sql) if sql else ''),args
    def get_sources(self,sources):
        out=[]
        with self.lock:
            for source in sources:
                rows=self.con.execute('select * from docs where source=? order by case when kind like \'resource:%\' then 0 when kind=\'model_inference\' then 1 when kind in (\'speech\',\'third_party_speech_segment\') then 2 when kind=\'caption\' then 3 else 4 end,locator,id limit 20',(source,)).fetchall()
                if rows:out.append(self._card(rows[0],rows[:8]))
        return out
    def contextual_sources(self,question,queries,selected):
        relevant=self.search(question,queries,{'_sources':selected},limit=len(selected))
        ranked={c['source']:c for c in relevant}
        baseline={c['source']:c for c in self.get_sources(selected)}
        out=[]
        for source in selected:
            if source not in baseline:continue
            card=ranked.get(source,baseline[source]);existing=card['evidence'];extra=baseline[source]['evidence']
            card['evidence']=list({e['id']:e for e in existing[:5]+extra}.values())[:8]
            out.append(card)
        return out
    @staticmethod
    def _card(row, evidence):
        return {'source':row['source'],'creator':row['creator'],'published':row['published'],'saved':row['saved'],'status':row['status'],'evidence':[{'id':x['id'],'kind':x['kind'],'locator':x['locator'],'text':x['text']} for x in evidence]}
    def search(self,q,queries,filters,limit=8,enumerate_all=False,offset=0):
        where,args=self._filter(filters);rankings=[];lex_sources=set();hits={};qv=self.models.embed(queries,query=True)
        with self.lock:
            for phrase in queries:
                words=terms(phrase)
                if not words:continue
                expr=' OR '.join('"'+w.replace('"','')+'"' for w in words)
                rows=self.con.execute('select d.id,d.source from lex join docs d on d.id=lex.id where lex match ?'+where+' order by bm25(lex) limit 500',(expr,*args)).fetchall()
                rankings.append([r['id'] for r in rows[:60]]);lex_sources.update(r['source'] for r in rows)
            # Exact cosine scan in bounded blocks: small private index, no production vector extension.
            import heapq
            heaps=[[] for _ in queries]
            cur=self.con.execute('select d.id,d.source,d.vector from docs d where 1=1'+where,args)
            while (batch:=cur.fetchmany(256)):
                matrix=np.stack([np.frombuffer(r['vector'],dtype='float32') for r in batch]);norm=np.linalg.norm(matrix,axis=1);qn=np.linalg.norm(qv,axis=1)
                sims=(matrix@qv.T)/np.maximum(norm[:,None]*qn[None,:],1e-8)
                for i in range(len(queries)):
                    for row,score in zip(batch,sims[:,i]):
                        if float(score)<.25:continue
                        h=heaps[i];item=(float(score),row['id'])
                        if len(h)<60:heapq.heappush(h,item)
                        elif item>h[0]:heapq.heapreplace(h,item)
            rankings.extend([[item[1] for item in sorted(h,reverse=True)] for h in heaps]);fused=reciprocal_rank(rankings)
            # Rerank best 20 distinct source candidates, not 20 nearly identical frames.
            for key in fused:
                row=self.con.execute('select * from docs where id=?',(key,)).fetchone()
                if row is not None:hits.setdefault(row['source'],[]).append(row)
            candidates=list(hits)[:20]
            if enumerate_all:
                # Exact lexical enumeration, not a claim of exhaustive semantic recall.
                # Scan all matching source IDs, then paginated evidence and map/reduce in caller.
                lex_sources=set()
                for phrase in queries:
                    ws=terms(phrase)
                    if not ws:continue
                    expr=' OR '.join('"'+w+'"' for w in ws)
                    lex_sources.update(r[0] for r in self.con.execute('select distinct d.source from lex join docs d on d.id=lex.id where lex match ?'+where,(expr,*args)))
                ordered=list(dict.fromkeys([s for s in hits if s in lex_sources]+sorted(lex_sources)))
                return {'results':self.get_sources(ordered[offset:offset+limit]),'total_keyword_matches':len(ordered),'next_offset':offset+limit if offset+limit<len(ordered) else None}
            if not candidates:return []
            scores=self.models.rerank(q,['\n'.join(x['text'][:1300] for x in hits[s][:4]) for s in candidates]);order=sorted(range(len(candidates)),key=lambda i:(-float(scores[i]),i))
            return [self._card(hits[candidates[i]][0],hits[candidates[i]][:8]) for i in order[:limit]]
