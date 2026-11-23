"""Offline evidence store and queue. Supabase migration ships separately.

Default: local SQLite file only. Never connects to any existing remote database.
"""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import hashlib,json,sqlite3,datetime,re,os

def digest(*parts)->str:
    return hashlib.sha256('\x00'.join(str(p) for p in parts).encode()).hexdigest()[:32]

def utc()->str:return datetime.datetime.now(datetime.timezone.utc).isoformat()

class KnowledgeStore:
    def __init__(self, path: str|Path):
        p=Path(path)
        # Do not follow aliases into another project or overwrite shared data.
        if p.is_symlink():
            raise ValueError('refusing symlink database target')
        p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if p.parent.is_symlink():
            raise ValueError('refusing symlink database directory')
        created=not p.exists()
        if p.exists() and not p.is_file():
            raise ValueError('database path must be a regular file')
        self.path=p
        self.con=sqlite3.connect(str(p),isolation_level=None)
        if created and os.name=='posix':
            os.chmod(p,0o600)
        self.con.row_factory=sqlite3.Row
        self.con.execute('PRAGMA foreign_keys=ON')
        self.con.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,source_ref TEXT NOT NULL,kind TEXT NOT NULL,content_sha TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,link_only INTEGER NOT NULL DEFAULT 0,UNIQUE(tenant,source_ref,content_sha));
        CREATE TABLE IF NOT EXISTS evidence(id TEXT NOT NULL,source_id TEXT NOT NULL REFERENCES sources(id),kind TEXT NOT NULL,locator TEXT NOT NULL,verbatim TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(id,source_id));
        CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,canonical_url TEXT NOT NULL,name TEXT NOT NULL,purpose TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'seen',verification_receipt TEXT,created_at TEXT NOT NULL,UNIQUE(tenant,canonical_url));
        CREATE TABLE IF NOT EXISTS citations(tenant TEXT NOT NULL,resource_id TEXT NOT NULL REFERENCES resources(id),evidence_id TEXT NOT NULL,source_id TEXT NOT NULL REFERENCES sources(id),PRIMARY KEY(tenant,resource_id,evidence_id,source_id));
        CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,resource_id TEXT NOT NULL REFERENCES resources(id),evidence_id TEXT NOT NULL,source_id TEXT NOT NULL REFERENCES sources(id),field_type TEXT NOT NULL,value TEXT NOT NULL,verbatim_quote TEXT NOT NULL,claim_status TEXT NOT NULL DEFAULT 'source_claim');
        CREATE INDEX IF NOT EXISTS idx_facts_resource ON facts(tenant,resource_id);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,tenant TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,idempotency_key TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',started_at TEXT,finished_at TEXT,error TEXT,UNIQUE(tenant,kind,idempotency_key));
        CREATE INDEX IF NOT EXISTS idx_sources_tenant ON sources(tenant);
        CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
        CREATE INDEX IF NOT EXISTS idx_resources_tenant_url ON resources(tenant,canonical_url);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(tenant,status);
        CREATE TABLE IF NOT EXISTS archive_payloads(
           tenant TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id),
           original_text TEXT NOT NULL, content_sha256 TEXT NOT NULL, stored_at TEXT NOT NULL,
           PRIMARY KEY(tenant,source_id));
        CREATE TABLE IF NOT EXISTS reel_mentions(
           id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
           conversation_source_id TEXT NOT NULL REFERENCES sources(id),
           reel_source_id TEXT NOT NULL REFERENCES sources(id),
           locator TEXT NOT NULL, char_offset INTEGER NOT NULL CHECK(char_offset>=0),
           context TEXT NOT NULL,
           UNIQUE(tenant,conversation_source_id,reel_source_id,char_offset));
        CREATE INDEX IF NOT EXISTS idx_reel_mentions_lookup ON reel_mentions(tenant,reel_source_id);
        CREATE TABLE IF NOT EXISTS reel_processing(
          id TEXT PRIMARY KEY, tenant TEXT NOT NULL,
          reel_source_id TEXT NOT NULL REFERENCES sources(id),
          result_source_id TEXT NOT NULL REFERENCES sources(id),
          media_sha256 TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN('processed','partial')),
          processed_at TEXT NOT NULL,
          UNIQUE(tenant,reel_source_id,result_source_id,media_sha256));
        CREATE INDEX IF NOT EXISTS idx_reel_processing_lookup ON reel_processing(tenant,reel_source_id);
        ''')
        # Non-destructive compatibility migration for the v0.3 SQLite seed.
        known_columns={r['name'] for r in self.con.execute('PRAGMA table_info(sources)')}
        if 'link_only' not in known_columns:
            self.con.execute('ALTER TABLE sources ADD COLUMN link_only INTEGER NOT NULL DEFAULT 0')
            self.con.execute("UPDATE sources SET link_only=1 WHERE status='awaiting_authorized_media'")
    def close(self):self.con.close()
    @contextmanager
    def transaction(self):
        self.con.execute('BEGIN IMMEDIATE')
        try:yield;self.con.execute('COMMIT')
        except BaseException:self.con.execute('ROLLBACK');raise
    def store(self,tenant:str,source_ref:str,kind:str,source_text:str,observations,accepted,status='evidence_saved') ->str:
        sha=hashlib.sha256(source_text.encode()).hexdigest()
        sid=digest(tenant,kind,source_ref,sha)
        with self.transaction():
            self.con.execute('INSERT OR IGNORE INTO sources (id,tenant,source_ref,kind,content_sha,status,created_at,link_only) VALUES (?,?,?,?,?,?,?,?)',(sid,tenant,source_ref,kind,sha,status,utc(),int(status=='awaiting_authorized_media')))
            lookup={ev.uid:ev for ev in observations}
            for ev in observations:
                self.con.execute('INSERT OR IGNORE INTO evidence VALUES (?,?,?,?,?,?)',(ev.uid,sid,ev.kind,ev.locator,ev.text,utc()))
            for x in accepted:
                rid=digest(tenant,x.url)
                self.con.execute('INSERT OR IGNORE INTO resources VALUES (?,?,?,?,?,?,?,?)',(rid,tenant,x.url,x.name,x.purpose,'seen',None,utc()))
                for evid in x.evidence_ids:
                    if evid in lookup:
                        self.con.execute('INSERT OR IGNORE INTO citations VALUES (?,?,?,?)',(tenant,rid,evid,sid))
        return sid
    def counts(self,tenant:str)->dict:
        return {name:self.con.execute(f'SELECT COUNT(*) FROM {name} '+('WHERE tenant=?' if name!='evidence' else 'WHERE source_id IN (SELECT id FROM sources WHERE tenant=?)'),(tenant,)).fetchone()[0] for name in ('sources','evidence','resources','jobs')}
    def search(self,query:str,tenant:str,limit:int=20)->list[dict]:
        tokens=list(dict.fromkeys(t.lower() for t in re.findall(r'[A-Za-z0-9_]+',query) if len(t)>2))[:12]
        if not tokens:return []
        result=[]
        rows=self.con.execute('''SELECT r.id resource_id,r.name,r.canonical_url,r.purpose,r.status,s.source_ref,e.locator,e.verbatim evidence,e.kind evidence_kind
          FROM resources r JOIN citations c ON r.id=c.resource_id AND r.tenant=c.tenant
          JOIN sources s ON c.source_id=s.id AND s.tenant=r.tenant
          JOIN evidence e ON e.id=c.evidence_id AND e.source_id=s.id WHERE r.tenant=?''',(tenant,)).fetchall()
        seen=set()
        for row in rows:
            doc=' '.join(str(row[k]) for k in ('name','canonical_url','purpose','evidence')).lower()
            name=row['name'].lower();url=row['canonical_url'].lower();purpose=row['purpose'].lower();evidence=row['evidence'].lower()
            score=sum((5 if re.search(r'(?<![a-z0-9])'+re.escape(token)+r'(?![a-z0-9])',name) else (2 if token in name else 0))
                      +(1.5 if token in url else 0)+(0.35 if token in purpose else 0)+(0.1 if token in evidence else 0)
                      for token in tokens)
            if query.lower().strip() in name:score+=7
            if score==0:continue
            ident=(row['resource_id'],row['source_ref'],row['locator'])
            if ident in seen:continue
            seen.add(ident)
            obj=dict(row);obj['score']=round(score/(len(tokens) or 1),4)
            obj['facts']=[dict(x) for x in self.con.execute('SELECT field_type,value,verbatim_quote,claim_status FROM facts WHERE tenant=? AND resource_id=? ORDER BY rowid LIMIT 40',(tenant,row['resource_id'])).fetchall()]
            result.append(obj)
        result.sort(key=lambda x:(x['score'],x['status']!='seen',x['canonical_url']),reverse=True)
        return result[:min(limit,100)]
    def store_facts(self,source_id:str,tenant:str,claims:list):
        count=0
        with self.transaction():
            for c in claims:
                from .contracts import canonical_resource
                url=canonical_resource(c.resource_url)
                rid=digest(tenant,url)
                exists=self.con.execute('''SELECT 1 FROM citations WHERE tenant=? AND resource_id=? AND evidence_id=? AND source_id=?''',(tenant,rid,c.evidence_id,source_id)).fetchone()
                # A quote from a different reel slide can support a claim only after
                # that slide has been explicitly linked to the cited resource.
                if not exists:
                    associated=self.con.execute('SELECT 1 FROM citations WHERE tenant=? AND resource_id=? AND source_id=? LIMIT 1',(tenant,rid,source_id)).fetchone()
                    same_source=self.con.execute('SELECT 1 FROM evidence WHERE id=? AND source_id=?',(c.evidence_id,source_id)).fetchone()
                    if not associated or not same_source:continue
                fid=digest(tenant,rid,c.evidence_id,c.field_type,c.value)
                self.con.execute('INSERT OR IGNORE INTO facts VALUES (?,?,?,?,?,?,?,?,?)',(fid,tenant,rid,c.evidence_id,source_id,c.field_type,c.value,c.verbatim_quote,'source_claim'))
                count+=1
        return count
    def archive_source_text(self, source_id: str, tenant: str, text: str) -> None:
        # Ensure the original conversation body corresponds to the archive source.
        sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        with self.transaction():
            source = self.con.execute('SELECT content_sha,kind FROM sources WHERE id=? AND tenant=?', (source_id, tenant)).fetchone()
            if source is None or source['kind'] != 'conversation_archive' or source['content_sha'] != sha:
                raise ValueError('source/hash mismatch; refusing archive write')
            existing = self.con.execute('SELECT content_sha256 FROM archive_payloads WHERE source_id=? AND tenant=?', (source_id, tenant)).fetchone()
            if existing and existing['content_sha256'] != sha:
                raise ValueError('archive payload mismatch')
            self.con.execute('INSERT OR IGNORE INTO archive_payloads VALUES (?,?,?,?,?)', (tenant, source_id, text, sha, utc()))

    def get_archive_text(self, source_id: str, tenant: str) -> str | None:
        row = self.con.execute('''SELECT p.original_text FROM archive_payloads p
             JOIN sources s ON s.id=p.source_id AND s.tenant=p.tenant
             WHERE p.source_id=? AND p.tenant=?''', (source_id, tenant)).fetchone()
        return row['original_text'] if row else None

    def record_reel_mention(self, tenant: str, conversation_source_id: str,
                            reel_source_id: str, locator: str, char_offset: int, context: str) -> str:
        if not isinstance(char_offset, int) or char_offset < 0:
            raise ValueError('invalid mention position')
        rid = digest(tenant, conversation_source_id, reel_source_id, char_offset)
        with self.transaction():
            archive = self.con.execute('SELECT kind FROM sources WHERE tenant=? AND id=?', (tenant, conversation_source_id)).fetchone()
            reel = self.con.execute('SELECT kind FROM sources WHERE tenant=? AND id=?', (tenant, reel_source_id)).fetchone()
            if archive is None or archive['kind'] != 'conversation_archive' or reel is None or reel['kind'] not in ('reel','carousel','p','tv'):
                raise ValueError('source ownership or type mismatch')
            self.con.execute('INSERT OR IGNORE INTO reel_mentions VALUES (?,?,?,?,?,?,?)',
                             (rid, tenant, conversation_source_id, reel_source_id, locator, char_offset, context))
        return rid

    def context_for_reel(self, url: str, tenant: str, limit: int = 500) -> list[dict]:
        from .sources import canonicalize_instagram
        canon = canonicalize_instagram(url)
        rows = self.con.execute('''SELECT rm.locator,rm.char_offset,rm.context,
               archive.source_ref AS conversation_source,
               archive.id AS conversation_source_id,rm.reel_source_id
               FROM reel_mentions rm
               JOIN sources reel ON reel.id=rm.reel_source_id AND reel.tenant=rm.tenant
               JOIN sources archive ON archive.id=rm.conversation_source_id AND archive.tenant=rm.tenant
               WHERE rm.tenant=? AND reel.source_ref=? ORDER BY archive.created_at,rm.char_offset
               LIMIT ?''', (tenant, canon, max(1,min(limit,2000)))).fetchall()
        return [dict(row) | {'provenance':'user_provided_note_not_reel_evidence'} for row in rows]

    def mark_media_processed(self, tenant: str, reel_source_id: str, result_source_id: str,
                             media_sha256: str, partial: bool = False,
                             model_only_partial: bool = False) -> str:
        # Strict default: no model-only receipt. The explicit partial-only
        # exception records a REAL acquired asset plus model observation,
        # never a verified or fully processed Reel.
        if not re.fullmatch(r'[0-9a-f]{64}', media_sha256):
            raise ValueError('media hash must be a SHA-256 hex digest')
        rid = digest(tenant, reel_source_id, result_source_id, media_sha256)
        with self.transaction():
            link = self.con.execute('SELECT source_ref,kind,status,link_only FROM sources WHERE id=? AND tenant=?', (reel_source_id,tenant)).fetchone()
            result = self.con.execute('SELECT source_ref,kind,status,link_only FROM sources WHERE id=? AND tenant=?', (result_source_id,tenant)).fetchone()
            if not link or not result or link['source_ref'] != result['source_ref'] or link['kind'] not in ('reel','carousel') or result['kind'] != link['kind'] or reel_source_id == result_source_id or not link['link_only'] or result['link_only']:
                raise ValueError('media result does not belong to this reel')
            original = self.con.execute('''SELECT COUNT(*) AS count FROM evidence WHERE source_id=?
                AND kind IN ('ocr','asr','caption','manual','verified_doc')
                AND length(trim(verbatim))>0''', (result_source_id,)).fetchone()['count']
            if original == 0:
                model_count = self.con.execute('''SELECT COUNT(*) AS count FROM evidence WHERE source_id=?
                    AND kind='model_inference' AND length(trim(verbatim))>0''',
                    (result_source_id,)).fetchone()['count']
                if not (partial and model_only_partial and model_count>0):
                    raise ValueError('missing non-generative evidence; cannot mark media processed')
            status = 'partial' if partial else 'processed'
            self.con.execute('INSERT OR IGNORE INTO reel_processing VALUES (?,?,?,?,?,?,?)',
                             (rid,tenant,reel_source_id,result_source_id,media_sha256,status,utc()))
            # Never downgrade a previously completed Reel because one later pass fails.
            new_link_state = 'media_processed' if (not partial or link['status']=='media_processed') else 'partial'
            self.con.execute('UPDATE sources SET status=? WHERE id=? AND tenant=?', (new_link_state,reel_source_id,tenant))
            job_state = 'done' if new_link_state=='media_processed' else 'partial'
            self.con.execute('''UPDATE jobs SET status=?,finished_at=?
                WHERE tenant=? AND kind='await_permitted_media' AND idempotency_key=?''',
                (job_state,utc(),tenant,link['source_ref']))
        return rid

    def processing_history(self, url: str, tenant: str)->list[dict]:
        from .sources import canonicalize_instagram
        canon = canonicalize_instagram(url)
        rows = self.con.execute('''SELECT p.result_source_id,p.media_sha256,p.status,p.processed_at
            FROM reel_processing p JOIN sources s ON s.id=p.reel_source_id AND s.tenant=p.tenant
            WHERE p.tenant=? AND s.source_ref=? ORDER BY p.processed_at DESC''',(tenant,canon)).fetchall()
        return [dict(x) for x in rows]

    def pending_reels(self, tenant: str, limit: int = 100) -> list[dict]:
        rows = self.con.execute('''SELECT s.id,s.source_ref,s.kind,s.status,
               COUNT(rm.id) AS user_note_mentions, j.status AS pending_job_status
               FROM sources s LEFT JOIN reel_mentions rm ON rm.reel_source_id=s.id AND rm.tenant=s.tenant
               LEFT JOIN jobs j ON j.tenant=s.tenant AND j.kind='await_permitted_media'
                    AND j.idempotency_key=s.source_ref
               WHERE s.tenant=? AND s.link_only=1 AND s.status IN ('awaiting_authorized_media','partial')
               GROUP BY s.id,s.source_ref,s.kind,s.status,j.status
               ORDER BY s.created_at LIMIT ?''', (tenant, max(1,min(limit,1000)))).fetchall()
        return [dict(x) for x in rows]

    def set_verification(self,rid:str,tenant:str,status:str,receipt:dict|None):
        if status not in ('exists','readme_checked','sandbox_run','user_confirmed','unresolved'):
            raise ValueError('invalid verification state')
        if status!='unresolved':
            if not isinstance(receipt,dict) or not all(receipt.get(k) for k in ('provider','checked_at')):
                raise ValueError('promotion requires a named provider and dated receipt')
            if status in ('exists','readme_checked'):
                if receipt.get('http_status') != 200 or receipt.get('exists') is False:
                    raise ValueError('a missing or failed repository cannot be marked verified')
                if status=='readme_checked' and not receipt.get('readme_sha256'):
                    raise ValueError('README verification needs a content hash')
            if status=='sandbox_run' and not all(k in receipt for k in ('sandbox_id','artifact_sha256','exit_code')):
                raise ValueError('sandbox_run must include an isolated execution receipt')
            if status=='user_confirmed' and not receipt.get('confirmation_id'):
                raise ValueError('user_confirmed needs an explicit confirmation receipt')
        with self.transaction():
            cur=self.con.execute('UPDATE resources SET status=?,verification_receipt=? WHERE id=? AND tenant=?',(status,json.dumps(receipt) if receipt else None,rid,tenant))
            if cur.rowcount!=1:raise KeyError('resource not found for tenant')
    def enqueue(self,tenant:str,kind:str,payload:dict,key:str)->str:
        jid=digest(tenant,kind,key)
        with self.transaction():
            row=self.con.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()
            if row and json.loads(row['payload'])!=payload:raise ValueError('same idempotency key with different payload')
            self.con.execute('INSERT OR IGNORE INTO jobs(id,tenant,kind,payload,idempotency_key,status) VALUES (?,?,?,?,?,?)',(jid,tenant,kind,json.dumps(payload,sort_keys=True),key,'queued'))
        return jid
    def claim_job(self,tenant:str)->dict|None:
        with self.transaction():
            row=self.con.execute("SELECT * FROM jobs WHERE tenant=? AND status='queued' ORDER BY rowid LIMIT 1",(tenant,)).fetchone()
            if row is None:return None
            self.con.execute("UPDATE jobs SET status='running',started_at=? WHERE id=? AND status='queued'",(utc(),row['id']))
            return dict(row)
    def finish_job(self,jid:str,tenant:str,success:bool,error:str|None=None):
        with self.transaction():
            cur=self.con.execute("UPDATE jobs SET status=?,finished_at=?,error=? WHERE id=? AND tenant=? AND status='running'",('done' if success else 'failed',utc(),error,jid,tenant))
            if cur.rowcount!=1:raise ValueError('job was not running')
    def job(self,jid:str,tenant:str)->dict|None:
        x=self.con.execute('SELECT * FROM jobs WHERE id=? AND tenant=?',(jid,tenant)).fetchone()
        return dict(x) if x else None
