"""Server-only RPC adapter. No arbitrary SQL generation; no direct core writes."""
from datetime import date
import hashlib,re
from .core import Document,canonical_instagram

FILTERS={'creator','date_from','date_to','published_from','published_to','status','tool'}
def filter_args(f):
    out={}
    for k,v in (f or {}).items():
        if k not in FILTERS or not isinstance(v,str):raise ValueError('Unsupported filter')
        v=v.strip()
        if not v:continue
        if k.endswith(('_from','_to')):v=date.fromisoformat(v).isoformat()
        elif k=='creator':v=v.lstrip('@');assert_len(v,100)
        elif k=='status' and v not in ('completed','partial_media','media_pending'):raise ValueError('Invalid processing status')
        else:assert_len(v,120)
        out[k]=v
    for prefix in ('date','published'):
        if out.get(prefix+'_from','')>out.get(prefix+'_to','9999-12-31'):raise ValueError('Invalid date range')
    return out

def assert_len(s,n):
    if not 1<=len(s)<=n:raise ValueError('Input length invalid')

def split_text(s,n=1400):
    s=s.strip()
    # Retain all text; overlap prevents losing a procedure at a chunk boundary.
    for start in range(0,len(s),n-160):
        part=s[start:start+n]
        if part.strip():yield part
        if start+n>=len(s):break

class Database:
    def __init__(self,dsn,ca_cert):
        if not ca_cert:raise RuntimeError('Configure the Supabase CA certificate for TLS verification.')
        self.dsn=dsn;self.ca_cert=ca_cert
    def _call(self,sql,params=(),write=False):
        import psycopg
        from psycopg.rows import dict_row
        with psycopg.connect(self.dsn,connect_timeout=8,row_factory=dict_row,sslmode='verify-full',sslrootcert=self.ca_cert,options='-c statement_timeout=15000') as conn:
            if not write:conn.execute('set transaction read only')
            return conn.execute(sql,params).fetchall()
    def versions(self,after=''):
        return self._call('select * from reelbrain_studio.sources(%s,%s)',(after,100))
    def evidence(self,source,after=''):
        return self._call('select * from reelbrain_studio.evidence(%s,%s,%s)',(source,after,300))
    def stats(self,filters):
        from psycopg.types.json import Jsonb
        rows=self._call('select * from reelbrain_studio.counts(%s)',(Jsonb(filters),));return rows[0] if rows else {}
    def submit(self,raw):
        source=canonical_instagram(raw)
        rows=self._call('select * from reelbrain_studio.submit_url(%s)',(source,),write=True);return rows[0]
    def refresh(self,index,max_sources=25):
        # Each source version is checked; index changes only for modified sources.
        after='';changed=0;scanned=0
        while True:
            rows=self.versions(after)
            if not rows:break
            for row in rows:
                source=row['source_url'];after=source;scanned+=1;version=str(row['version'])
                if index.version(source)==version:continue
                if changed>=max_sources:return {'changed':changed,'scanned':scanned,'more_pending':True}
                docs=[];cursor='';seen=set()
                def add(key,kind,loc,txt):
                    if not isinstance(txt,str) or not txt.strip():return
                    for pos,part in enumerate(split_text(txt)):
                        # preserve first source locator, avoid repeated identical OCR noise
                        if (kind,part) in seen:continue
                        seen.add((kind,part));id=hashlib.sha256(f'{source}|{key}|{pos}'.encode()).hexdigest()
                        docs.append(Document(id,source,row['creator'] or '',str(row['published'] or ''),str(row['saved'] or ''),row['stage'] or '',kind,loc,part))
                add('caption','caption','creator-caption',row.get('caption'));add('hosted','speech','hosted-asr',row.get('speech'));add('external','external_topic_research','saved external research',row.get('research'))
                while True:
                    batch=self.evidence(source,cursor)
                    for ev in batch:
                        cursor=ev['evidence_id'];add(cursor,ev['kind'],ev['locator'],ev['body'])
                    if len(batch)<300:break
                index.replace_source(source,docs,version);changed+=1
            if len(rows)<100:break
        return {'changed':changed,'scanned':scanned,'more_pending':False}
