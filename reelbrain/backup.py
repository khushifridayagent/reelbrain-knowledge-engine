"""Private, non-overwriting, offline SQLite backup and restore with verification.

This is NOT Supabase/PITR backup, never reaches any remote service, and never
replaces an existing database. Original conversations remain plaintext at rest;
protect both the original and backup files outside the repository.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from contextlib import closing
from urllib.parse import quote
from .store import KnowledgeStore

_REQUIRED={'sources','evidence','resources','archive_payloads','reel_mentions','reel_processing','jobs'}

def _digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def _safe_destination(path:str|Path)->Path:
    target=Path(path)
    if target.is_symlink() or target.exists():
        raise FileExistsError(f'refusing to overwrite existing destination: {target}')
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if target.parent.is_symlink():
        raise ValueError('refusing symlink destination directory')
    return target

def _temp_near(target:Path)->Path:
    fd,name=tempfile.mkstemp(prefix='.reelbrain-',suffix='.tmp',dir=target.parent)
    os.close(fd)
    if os.name=='posix':os.chmod(name,0o600)
    return Path(name)

def verify_database(path:str|Path)->dict:
    p=Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError('not a regular SQLite backup file')
    # Read-only SQLite URI, no DB creation on invalid file paths.
    uri='file:'+quote(str(p.resolve()),safe='/')+'?mode=ro'
    try:
        with closing(sqlite3.connect(uri,uri=True,timeout=10)) as con:
            integrity=con.execute('PRAGMA integrity_check').fetchone()[0]
            present={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if integrity!='ok' or not _REQUIRED.issubset(present):
                raise ValueError('corrupt or incompatible Reelbrain database')
            counts={table:con.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                    for table in ('sources','evidence','resources','archive_payloads','reel_mentions','reel_processing','jobs')}
    except sqlite3.DatabaseError as exc:
        raise ValueError('corrupt or inaccessible SQLite database') from exc
    return {'integrity':'ok','sha256':_digest(p),'source_counts':counts}

def _publish_exclusive(temp:Path,target:Path):
    # Same filesystem: hard-link creation is atomic and refuses an existing path.
    # Unlike rename/replace, it cannot destroy a pre-existing project file.
    os.link(temp,target)
    if os.name=='posix':os.chmod(target,0o600)

def backup_database(store:KnowledgeStore,destination:str|Path)->dict:
    target=_safe_destination(destination)
    temp=_temp_near(target)
    try:
        with closing(sqlite3.connect(temp)) as mirror:
            store.con.backup(mirror)
        receipt=verify_database(temp)
        _publish_exclusive(temp,target)
        return receipt | {'destination_name':target.name,'backup_type':'offline_sqlite_snapshot'}
    finally:
        temp.unlink(missing_ok=True)

def restore_database(backup_path:str|Path,new_database_path:str|Path)->dict:
    backup=Path(backup_path)
    verified=verify_database(backup)
    target=_safe_destination(new_database_path)
    temp=_temp_near(target)
    try:
        shutil.copyfile(backup,temp)
        if _digest(temp)!=verified['sha256']:
            raise ValueError('copied backup checksum mismatch')
        result=verify_database(temp)
        _publish_exclusive(temp,target)
        return result | {'destination_name':target.name,'restore_type':'fresh_path_only'}
    finally:
        temp.unlink(missing_ok=True)
