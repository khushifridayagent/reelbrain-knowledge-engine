"""Bounded, no-extract ZIP research import, safe for large historical report archives.

ZIP contents are always treated as untrusted source text, not executable
instructions; archive paths are only virtual provenance labels.
"""
from __future__ import annotations
from pathlib import Path, PurePosixPath
import stat,zipfile

class ArchiveRejected(ValueError):pass

_ALLOWED_EXT={'.md','.markdown','.txt','.csv','.tsv','.json','.jsonl'}

def _validate_member(info:zipfile.ZipInfo,max_member_bytes:int):
    name=info.filename
    parts=PurePosixPath(name).parts
    if '\\' in name or name.startswith('/') or not parts or any(x in ('..','.') for x in parts) or ':' in parts[0]:
        raise ArchiveRejected(f'unsafe ZIP member path: {name!r}')
    if info.flag_bits & 0x1:raise ArchiveRejected('encrypted ZIP member unsupported')
    mode=info.external_attr >> 16
    if stat.S_ISLNK(mode):raise ArchiveRejected('ZIP symlinks are forbidden')
    if info.file_size>max_member_bytes:raise ArchiveRejected(f'ZIP member too large: {name}')
    if info.file_size>1_000_000 and info.file_size/max(info.compress_size,1)>500:
        raise ArchiveRejected('suspicious ZIP compression ratio')
    return PurePosixPath(name).suffix.lower() in _ALLOWED_EXT


def import_research_zip(path:str|Path,pipeline,tenant:str='personal',*,max_member_bytes:int=10*1024*1024,
                        max_total_bytes:int=100*1024*1024,max_entries:int=5000)->dict:
    file=Path(path)
    if not file.is_file() or not zipfile.is_zipfile(file):raise ArchiveRejected('not a readable local ZIP archive')
    with zipfile.ZipFile(file) as archive:
        entries=[x for x in archive.infolist() if not x.is_dir()]
        if len(entries)>max_entries:raise ArchiveRejected('ZIP contains too many entries')
        total=sum(x.file_size for x in entries)
        if total>max_total_bytes:raise ArchiveRejected('ZIP exceeds uncompressed data budget')
        # Fail before any DB changes when one member is obviously unsafe.
        allowed=[]
        for item in entries:
            if _validate_member(item,max_member_bytes):allowed.append(item)
        stats={'archive':file.name,'inspected_entries':len(entries),'eligible_documents':len(allowed),
               'imported_documents':0,'resource_mentions':0,'rejected_non_text':len(entries)-len(allowed),'bad_encoding':[]}
        for entry in allowed:
            raw=archive.read(entry)
            try:document=raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                # Stop with an explicit unknown; never silently discard content.
                stats['bad_encoding'].append(entry.filename)
                continue
            if not document.strip():continue
            reference=f'{file.name}::{entry.filename}'
            result=pipeline.ingest_report(reference,document,tenant=tenant)
            stats['imported_documents']+=1
            stats['resource_mentions']+=result['resource_count']
        return stats
