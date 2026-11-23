"""Durable local *authorized-upload-only* media queue.

No Instagram scraping. Files are handled by scoped job storage, with SHA-256
idempotency, media magic checks, status receipts, and a bounded size budget.
"""
from __future__ import annotations
import hashlib, json, io, os, re, tempfile, time
from pathlib import Path
from .store import KnowledgeStore, utc, digest
from .sources import canonicalize_instagram, InvalidSource

class MediaInboxError(ValueError):pass

_ALLOWED={'.png','.jpg','.jpeg','.webp','.mp4','.mov','.webm','.mkv'}
_MAX_BYTES=100*1024*1024

def _check_magic(file:Path,ext:str):
    with file.open('rb') as f:head=f.read(32)
    if ext=='.png':return head.startswith(b'\x89PNG\r\n\x1a\n')
    if ext in {'.jpg','.jpeg'}:return head.startswith(b'\xff\xd8\xff')
    if ext=='.webp':return head[:4]==b'RIFF' and head[8:12]==b'WEBP'
    if ext in {'.mp4','.mov'}:return head[4:8]==b'ftyp'
    if ext in {'.webm','.mkv'}:return head.startswith(b'\x1a\x45\xdf\xa3')
    return False

class MediaInbox:
    def __init__(self,db_path:str|Path,media_dir:str|Path,tenant:str='personal'):
        self.db=KnowledgeStore(db_path)
        directory=Path(media_dir)
        if directory.is_symlink():raise MediaInboxError('refusing symlink media store')
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        if directory.is_symlink():raise MediaInboxError('media directory changed into symlink')
        self.dir=directory
        self.tenant=tenant
        self.db.con.executescript('''
        CREATE TABLE IF NOT EXISTS media_intake_jobs(
          task_id TEXT PRIMARY KEY,tenant TEXT NOT NULL, source_url TEXT NOT NULL,
          media_sha256 TEXT NOT NULL,local_media_path TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('queued','processing','complete','partial','failed')),
          result_json TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          UNIQUE(tenant,source_url,media_sha256));
        CREATE INDEX IF NOT EXISTS idx_media_intake_work ON media_intake_jobs(tenant,status,created_at);
        ''')
    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

    def save_upload(self,stream,filename:str,url:str,max_bytes:int=_MAX_BYTES)->dict:
        if not isinstance(filename,str) or '/' in filename or '\\' in filename or '\x00' in filename or not filename:
            raise MediaInboxError('invalid filename')
        ext=Path(filename).suffix.lower()
        if ext not in _ALLOWED:raise MediaInboxError('unsupported media extension')
        try:canon=canonicalize_instagram(url)
        except InvalidSource as e:raise MediaInboxError(str(e)) from e
        if not 0<max_bytes<=_MAX_BYTES:raise MediaInboxError('invalid byte budget')
        temp_path=None
        try:
            fd,temp=tempfile.mkstemp(prefix='.pending_',suffix=ext,dir=str(self.dir))
            temp_path=Path(temp)
            if os.name=='posix':os.chmod(temp_path,0o600)
            size=0;sha=hashlib.sha256()
            with os.fdopen(fd,'wb') as target:
                while True:
                    chunk=stream.read(1<<20)
                    if not chunk:break
                    size+=len(chunk)
                    if size>max_bytes:raise MediaInboxError('media exceeds configured upload limit')
                    target.write(chunk);sha.update(chunk)
            if not size or not _check_magic(temp_path,ext):
                raise MediaInboxError('media file header does not match supported format')
            checksum=sha.hexdigest()
            task_id=digest(self.tenant,canon,checksum)
            final_path=self.dir/(task_id+ext)
            # Reuse matching object; no overwrite of another task's bytes.
            if final_path.exists():
                if final_path.is_symlink() or hashlib.sha256(final_path.read_bytes()).hexdigest()!=checksum:
                    raise MediaInboxError('media collision or tampered file')
                temp_path.unlink();temp_path=None
            else:
                os.replace(temp_path,final_path);temp_path=None
            now=utc()
            with self.db.transaction():
                self.db.con.execute('''INSERT OR IGNORE INTO media_intake_jobs
                (task_id,tenant,source_url,media_sha256,local_media_path,status,created_at,updated_at)
                VALUES(?,?,?,?,?,'queued',?,?)''',
                (task_id,self.tenant,canon,checksum,str(final_path),now,now))
            return self.get(task_id)
        finally:
            if temp_path is not None:temp_path.unlink(missing_ok=True)

    def get(self,task_id:str)->dict|None:
        row=self.db.con.execute('''SELECT task_id,source_url,media_sha256,status,result_json,error,created_at,updated_at
             FROM media_intake_jobs WHERE task_id=? AND tenant=?''',(task_id,self.tenant)).fetchone()
        if row is None:return None
        r=dict(row)
        if r['result_json']:
            r['result']=json.loads(r.pop('result_json'))
        else:r.pop('result_json')
        return r

    def list_tasks(self,limit:int=100)->list[dict]:
        rows=self.db.con.execute('''SELECT task_id FROM media_intake_jobs WHERE tenant=? ORDER BY created_at DESC LIMIT ?''',
                                 (self.tenant,min(100,max(1,limit)))).fetchall()
        return [self.get(row['task_id']) for row in rows]

    def process_one(self,task_id:str,*,engine=None)->dict:
        with self.db.transaction():
            current=self.db.con.execute('''SELECT local_media_path,source_url,media_sha256,status
                FROM media_intake_jobs WHERE task_id=? AND tenant=?''',(task_id,self.tenant)).fetchone()
            if current is None:raise MediaInboxError('task not found')
            if current['status']!='queued':return self.get(task_id)
            self.db.con.execute('''UPDATE media_intake_jobs SET status='processing',updated_at=?
                WHERE task_id=? AND tenant=? AND status='queued' ''',(utc(),task_id,self.tenant))
        try:
            p=Path(current['local_media_path'])
            if p.is_symlink() or not p.is_file() or p.parent.resolve()!=self.dir.resolve():
                raise MediaInboxError('media path left private staging area')
            checksum=hashlib.sha256(p.read_bytes()).hexdigest()
            if checksum!=current['media_sha256']:raise MediaInboxError('media hash mismatch')
            if engine is None:
                from .engine import LocalPipelineEngine
                engine=LocalPipelineEngine(self.db)
            result=engine.ingest(p,current['source_url'],self.tenant,allow_external=False)
            status='partial' if result.get('status')=='partial' else 'complete'
            err=None
        except Exception as exc:
            status='failed';err=(type(exc).__name__+': '+str(exc))[:250];result=None
        with self.db.transaction():
            self.db.con.execute('''UPDATE media_intake_jobs SET status=?,error=?,result_json=?,updated_at=?
                WHERE task_id=? AND tenant=? AND status='processing' ''',
                (status,err,json.dumps(result,ensure_ascii=False,default=str) if result else None,utc(),task_id,self.tenant))
        return self.get(task_id)

    def process_queued(self,limit:int=5)->list[dict]:
        ids=self.db.con.execute('''SELECT task_id FROM media_intake_jobs WHERE tenant=? AND status='queued'
            ORDER BY created_at LIMIT ?''',(self.tenant,max(0,min(limit,20)))).fetchall()
        return [self.process_one(row['task_id']) for row in ids]
