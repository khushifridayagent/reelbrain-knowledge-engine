"""Read the user's historical GitHub research *as unverified source material*.

No network, repository execution, subprocess, auto-install, or ZIP filesystem
extraction. Exact catalog URLs must be present in the source and remain ``seen``.
Data is private and tenant-isolated. Imports are idempotent by source ZIP SHA256.
"""
from __future__ import annotations
from datetime import date
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, BadZipFile
import json
import re
import stat

from .contracts import Observation, ResourceCandidate
from .pipeline import KnowledgePipeline
from .store import KnowledgeStore, utc

ROOT = 'GitHub_Trending_Two_Year_Intelligence/'
REQUIRED = {
    'catalog': 'data/repository_catalog_2406.json',
    'leaders': 'data/daily_leaders_731_days.json',
    'ranked': 'data/historical_ranked_entries.json',
    'captures': 'data/capture_provenance.json',
    'coverage': 'data/PROVENANCE_AND_COVERAGE.json',
}
_SLG = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
_MANIFEST_LINE = re.compile(r'([0-9a-f]{64})  (.+)\Z')

class TrendingImportRejected(ValueError):
    pass


def _day(value, field='date'):
    try: return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError, AttributeError):
        raise TrendingImportRejected(f'invalid {field}: {value!r}')


def _repo(value, field='repo'):
    if not isinstance(value,str) or not _SLG.fullmatch(value):
        raise TrendingImportRejected(f'invalid {field}: {str(value)[:100]!r}')
    return value


def _nonneg_int(x, field, allow_null=True):
    if x is None and allow_null: return None
    if type(x) is not int or x < 0:
        raise TrendingImportRejected(f'invalid {field} integer')
    return x


def _json(z, name):
    try: return json.loads(z.read(ROOT+name).decode('utf-8-sig'))
    except (UnicodeError, KeyError, json.JSONDecodeError) as exc:
        raise TrendingImportRejected(f'unreadable JSON member: {name}') from exc


def _load(path:Path):
    if not path.is_file() or not path.name.lower().endswith('.zip'):
        raise TrendingImportRejected('ZIP input must be an existing file')
    try:
        with ZipFile(path) as z:
            items=[i for i in z.infolist() if not i.is_dir()]
            if len(items)>2000 or sum(i.file_size for i in items)>120*1024*1024:
                raise TrendingImportRejected('ZIP entry count or uncompressed size exceeded')
            names={i.filename for i in items}
            if len(names)!=len(items):raise TrendingImportRejected('duplicate ZIP member names')
            for i in items:
                parts=PurePosixPath(i.filename).parts
                if ('\\' in i.filename or not i.filename.startswith(ROOT) or
                    not parts or any(p in ('..','.') for p in parts) or
                    stat.S_ISLNK(i.external_attr >> 16) or (i.flag_bits & 1) or
                    i.file_size>35*1024*1024 or
                    (i.file_size>1048576 and i.file_size/max(1,i.compress_size)>500)):
                    raise TrendingImportRejected('unsafe ZIP member or compression ratio')
            manifest=z.read(ROOT+'FILE_CHECKSUMS_SHA256.txt').decode('ascii')
            seen=set()
            for line in manifest.splitlines():
                m=_MANIFEST_LINE.fullmatch(line)
                if not m:raise TrendingImportRejected('bad checksums manifest syntax')
                expected,name=m.groups()
                if name in seen:raise TrendingImportRejected('duplicate manifest target')
                seen.add(name)
                if ROOT+name not in names or sha256(z.read(ROOT+name)).hexdigest()!=expected:
                    raise TrendingImportRejected(f'archive checksum mismatch: {name}')
            if not all(r in seen for r in REQUIRED.values()):
                raise TrendingImportRejected('manifest missing structured research files')
            data={k:_json(z,v) for k,v in REQUIRED.items()}
            raw_catalog=z.read(ROOT+REQUIRED['catalog']).decode('utf-8-sig')
    except (BadZipFile,KeyError,UnicodeError) as exc:
        raise TrendingImportRejected('invalid or incomplete historical research ZIP') from exc
    return data,raw_catalog,len(seen)


def _validate(data):
    repos,leaders,history,captures,coverage=(data[k] for k in ('catalog','leaders','ranked','captures','coverage'))
    if not all(isinstance(x,list) for x in (repos,leaders,history,captures)) or not isinstance(coverage,dict):
        raise TrendingImportRejected('structured arrays or coverage object missing')
    if len(repos)>250_000 or len(leaders)>20_000 or len(history)>500_000 or len(captures)>100_000:
        raise TrendingImportRejected('invalid record counts')
    catalog_seen=set()
    catalog_numbers=set()
    for idx,r in enumerate(repos):
        if not isinstance(r,dict):raise TrendingImportRejected('malformed catalog row')
        slug=_repo(r.get('repo'))
        if r.get('repo_url')!='https://github.com/'+slug:
            raise TrendingImportRejected(f'catalog row {idx} URL does not match exact repo identity')
        if slug in catalog_seen:
            raise TrendingImportRejected('exact duplicate catalog repo slug')
        catalog_seen.add(slug)
        number=_nonneg_int(r.get('catalog_number'),'catalog_number',False)
        if number in catalog_numbers:
            raise TrendingImportRejected('duplicate catalog number')
        catalog_numbers.add(number)
        for f in ('what_it_does','core_features','practical_use_cases','evidence','verification'):
            if not isinstance(r.get(f),str):raise TrendingImportRejected(f'missing {f}')
    seen_days=set()
    for r in leaders:
        if not isinstance(r,dict):raise TrendingImportRejected('malformed day row')
        day=_day(r.get('date'))
        if day in seen_days:raise TrendingImportRejected('duplicate day in leaders')
        seen_days.add(day)
        for f in ('primary_rank1','primary_gain_repo','secondary_rank1'):
            if r.get(f) is not None:_repo(r[f],f)
        for f in ('primary_rank1_gain','primary_gain','primary_gain_rank'):
            _nonneg_int(r.get(f),f)
    history_keys=set()
    for r in history:
        if not isinstance(r,dict):raise TrendingImportRejected('malformed history row')
        key=(_day(r.get('date')),r.get('source'),_nonneg_int(r.get('rank'),'rank',False),_repo(r.get('repo')))
        if key in history_keys:raise TrendingImportRejected('duplicate ranked history row')
        history_keys.add(key)
        for f in ('stars_today','historic_stars','historic_forks'):_nonneg_int(r.get(f),f)
    capture_keys=set()
    for r in captures:
        if not isinstance(r,dict):raise TrendingImportRejected('malformed capture row')
        key=(_day(r.get('date')),r.get('source'))
        if key in capture_keys:raise TrendingImportRejected('duplicate capture day/source')
        capture_keys.add(key)
        _nonneg_int(r.get('row_count'),'row_count')
    if coverage.get('calendar_days') is not None and coverage['calendar_days']!=len(leaders):
        raise TrendingImportRejected('coverage metadata disagrees with daily leader count')
    if (coverage.get('secondary_distinct_identifiers_in_original_catalog') is not None and
        coverage['secondary_distinct_identifiers_in_original_catalog']!=len(repos)):
        raise TrendingImportRejected('coverage metadata disagrees with catalog count')


def _schema(db:KnowledgeStore):
    db.con.executescript('''
    CREATE TABLE IF NOT EXISTS trend_archives(
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,archive_name TEXT NOT NULL,
      source_id TEXT NOT NULL,coverage_json TEXT NOT NULL,verified_manifest_count INTEGER NOT NULL,
      imported_at TEXT NOT NULL,PRIMARY KEY(tenant,archive_sha));
    CREATE TABLE IF NOT EXISTS trend_catalog(
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,repo TEXT NOT NULL,
      catalog_number INTEGER NOT NULL,repo_url TEXT NOT NULL,
      what_it_does TEXT NOT NULL,core_features TEXT NOT NULL,practical_use_cases TEXT NOT NULL,
      evidence TEXT NOT NULL,source_verification TEXT NOT NULL,
      verification_level TEXT NOT NULL DEFAULT 'supplied_unverified',
      source_locator TEXT NOT NULL,PRIMARY KEY(tenant,archive_sha,catalog_number),
      FOREIGN KEY(tenant,archive_sha) REFERENCES trend_archives(tenant,archive_sha));
    CREATE TABLE IF NOT EXISTS trend_leaders(
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,day TEXT NOT NULL,
      row_json TEXT NOT NULL,PRIMARY KEY(tenant,archive_sha,day));
    CREATE TABLE IF NOT EXISTS trend_ranked(
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,day TEXT NOT NULL,
      source TEXT NOT NULL,rank INTEGER NOT NULL,repo TEXT NOT NULL,
      row_json TEXT NOT NULL,PRIMARY KEY(tenant,archive_sha,day,source,rank,repo));
    CREATE TABLE IF NOT EXISTS trend_captures(
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,day TEXT NOT NULL,
      source TEXT NOT NULL,row_json TEXT NOT NULL,
      PRIMARY KEY(tenant,archive_sha,day,source));
    CREATE TABLE IF NOT EXISTS trend_verifications (
      tenant TEXT NOT NULL,archive_sha TEXT NOT NULL,repo TEXT NOT NULL,
      github_repository_id TEXT NOT NULL,readme_url TEXT NOT NULL,
      readme_sha TEXT NOT NULL,readme_claim TEXT NOT NULL,
      checked_at TEXT NOT NULL,execution_status TEXT NOT NULL DEFAULT 'not_tested',
      PRIMARY KEY(tenant,archive_sha,repo,readme_sha));
    CREATE INDEX IF NOT EXISTS idx_trend_verification_repo ON trend_verifications(tenant,repo);
    CREATE INDEX IF NOT EXISTS idx_trend_catalog_repo ON trend_catalog(tenant,repo);
    CREATE INDEX IF NOT EXISTS idx_trend_leaders_day ON trend_leaders(tenant,day);
    CREATE INDEX IF NOT EXISTS idx_trend_ranked_repo ON trend_ranked(tenant,repo);
    ''')


def import_trending_zip(path:str|Path,db:KnowledgeStore,tenant:str='personal')->dict:
    """All source JSON data retained without promoting unspecified features into facts."""
    path=Path(path)
    data,raw_catalog,verified_count=_load(path)
    _validate(data)  # Fail without any SQLite writes if archive is corrupt.
    archive_sha=sha256(path.read_bytes()).hexdigest()
    _schema(db)
    reference=f'{path.name}::{ROOT}{REQUIRED["catalog"]}'
    obs=[];candidates=[]
    for ix,record in enumerate(data['catalog']):
        url=record['repo_url']
        # The catalog provides exact URL proof; purpose/features are UNVERIFIED source assertions.
        observation=Observation(
            f"Repository: {record['repo']}\nExact supplied URL: {url}\n"
            f"Claimed purpose (not verified): {record['what_it_does']}\n"
            f"Claimed features (not verified): {record['core_features']}\n"
            f"Possible use cases (not verified): {record['practical_use_cases']}",
            kind='document',locator=f'{reference}#/{ix}')
        obs.append(observation)
        candidates.append(ResourceCandidate(record['repo'],url,
                         f"Supplied historical catalog; unverified: {record['what_it_does']}"))
    # Save evidence via existing contract, rather than creating unverifiable URLs by DB shortcuts.
    outcome=KnowledgePipeline(db).ingest_evidence(path.name,reference,'historical_github_catalog',
                                             obs,candidates,tenant=tenant,original=raw_catalog)
    if outcome['rejected']:
        raise TrendingImportRejected(f'catalog evidence gate rejected {len(outcome["rejected"])} links')
    sid=outcome['source_id']
    folded={}
    for r in data['catalog']:
        folded.setdefault(r['repo'].casefold(),set()).add(r['repo'])
    casefold_collisions=sum(len(variants)-1 for variants in folded.values() if len(variants)>1)
    with db.transaction():
        db.con.execute('''INSERT OR IGNORE INTO trend_archives
            (tenant,archive_sha,archive_name,source_id,coverage_json,verified_manifest_count,imported_at)
            VALUES(?,?,?,?,?,?,?)''',
            (tenant,archive_sha,path.name,sid,json.dumps(data['coverage'],sort_keys=True),verified_count,utc()))
        db.con.executemany('''INSERT OR IGNORE INTO trend_catalog
          (tenant,archive_sha,repo,catalog_number,repo_url,what_it_does,core_features,practical_use_cases,
           evidence,source_verification,verification_level,source_locator)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''', [
            (tenant,archive_sha,r['repo'],r['catalog_number'],r['repo_url'],r['what_it_does'],
             r['core_features'],r['practical_use_cases'],r['evidence'],r['verification'],
             'supplied_unverified',f'{reference}#/{i}') for i,r in enumerate(data['catalog'])])
        db.con.executemany('INSERT OR IGNORE INTO trend_leaders VALUES(?,?,?,?)', [
            (tenant,archive_sha,r['date'],json.dumps(r,ensure_ascii=False,sort_keys=True)) for r in data['leaders']])
        db.con.executemany('INSERT OR IGNORE INTO trend_ranked VALUES(?,?,?,?,?,?,?)', [
            (tenant,archive_sha,r['date'],r['source'],r['rank'],r['repo'],json.dumps(r,ensure_ascii=False,sort_keys=True)) for r in data['ranked']])
        db.con.executemany('INSERT OR IGNORE INTO trend_captures VALUES(?,?,?,?,?)', [
            (tenant,archive_sha,r['date'],r['source'],json.dumps(r,ensure_ascii=False,sort_keys=True)) for r in data['captures']])
    return {'status':'local_imported','archive_sha256':archive_sha,'archive_file':path.name,
            'manifest_files_verified':verified_count,'catalog_rows':len(data['catalog']),
            'daily_leader_rows':len(data['leaders']),'ranked_history_rows':len(data['ranked']),
            'capture_provenance_rows':len(data['captures']),'source_id':sid,
            'unique_resource_urls_seen':outcome['resource_count'],
            'casefold_identity_collisions':casefold_collisions,
            'verification_level':'supplied_unverified',
            'coverage_disclosure':data['coverage'],
            'remote_supabase_uploaded':False}


def trending_counts(db:KnowledgeStore,tenant='personal'):
    _schema(db)
    result={}
    for table,label in [('trend_catalog','catalog_rows'),('trend_leaders','daily_leader_rows'),
                        ('trend_ranked','ranked_history_rows'),('trend_captures','capture_provenance_rows'),
                        ('trend_archives','archive_count')]:
        result[label]=db.con.execute(f'SELECT count(*) FROM {table} WHERE tenant=?',(tenant,)).fetchone()[0]
    return result


def search_catalog(db:KnowledgeStore,query:str,tenant='personal',limit=15):
    _schema(db)
    q=query.strip()[:120]
    if not q:return []
    if not (1<=limit<=100):raise ValueError('limit must be 1..100')
    # Escape LIKE wildcards. README assertions stay separate from catalog claims.
    needle='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    sql="""SELECT c.repo,c.repo_url,c.what_it_does,c.core_features,c.practical_use_cases,
       c.evidence,c.source_verification,c.verification_level,c.source_locator,c.archive_sha,
       (SELECT v.readme_claim FROM trend_verifications v
        WHERE v.tenant=c.tenant AND v.archive_sha=c.archive_sha AND v.repo=c.repo
        ORDER BY v.checked_at DESC LIMIT 1) AS readme_claim
       FROM trend_catalog c WHERE c.tenant=? AND
       (c.repo LIKE ? ESCAPE '\\' OR c.what_it_does LIKE ? ESCAPE '\\'
        OR c.core_features LIKE ? ESCAPE '\\' OR EXISTS (
          SELECT 1 FROM trend_verifications v
          WHERE v.tenant=c.tenant AND v.archive_sha=c.archive_sha AND v.repo=c.repo
          AND v.readme_claim LIKE ? ESCAPE '\\'))
       ORDER BY CASE WHEN lower(c.repo)=lower(?) THEN 0 ELSE 1 END,
          CASE WHEN c.verification_level='readme_checked' THEN 0 ELSE 1 END,
          c.repo LIMIT ?"""
    return [dict(r) for r in db.con.execute(sql,(tenant,needle,needle,needle,needle,q,limit)).fetchall()]


def daily_lookup(db:KnowledgeStore,day:str,tenant='personal'):
    _schema(db)
    date_=_day(day)
    row=db.con.execute('''SELECT row_json FROM trend_leaders WHERE tenant=? AND day=?
        ORDER BY archive_sha DESC LIMIT 1''',(tenant,date_)).fetchone()
    return json.loads(row['row_json']) if row else None


def _literal(x):
    if x is None:return 'NULL'
    # data is treated as SQL string data, NEVER as executable SQL; postgres uses doubled quotes.
    value=str(x)
    if '\x00' in value:raise ValueError('NUL byte invalid in SQL text')
    return "'"+value.replace("'","''")+"'"


def export_supabase_sql(db:KnowledgeStore,out_dir:str|Path,tenant:str='personal',batch_size:int=100)->list[Path]:
    """Reversible remote import data scripts; schema migration must run first.

    Content is never auto-applied; these files are safe to inspect manually. The
    exact source catalog, history and provenance are preserved as source claims.
    """
    _schema(db)
    if not 1<=batch_size<=1000:raise ValueError('batch_size must be 1..1000')
    dest=Path(out_dir)
    if dest.is_symlink():raise ValueError('refusing symlink destination')
    dest.mkdir(parents=True,exist_ok=True)
    for old in dest.glob('reelbrain_import_*.sql'):
        raise FileExistsError(f'will not overwrite existing export: {old}')
    files=[];counter=0
    schemas=[
     ('trend_archives','archives',['archive_sha','archive_name','source_id','coverage_json','verified_manifest_count','imported_at'],['archive_sha','archive_name','source_id','coverage_json','verified_manifest_count','imported_at']),
     ('trend_catalog','catalog',['archive_sha','repo','catalog_number','repo_url','what_it_does','core_features','practical_use_cases','evidence','source_verification','verification_level','source_locator'],['archive_sha','repo','catalog_number','repo_url','what_it_does','core_features','practical_use_cases','evidence','source_verification','verification_level','source_locator']),
     ('trend_leaders','daily_leaders',['archive_sha','day','row_json'],['archive_sha','day','row_json']),
     ('trend_ranked','ranked_entries',['archive_sha','day','source','rank','repo','row_json'],['archive_sha','day','source','rank','repo','row_json']),
     ('trend_captures','capture_provenance',['archive_sha','day','source','row_json'],['archive_sha','day','source','row_json']),
    ]
    for local,remote,source_cols,target_cols in schemas:
        rows=db.con.execute('SELECT '+','.join(source_cols)+f' FROM {local} WHERE tenant=? ORDER BY archive_sha',(tenant,)).fetchall()
        for begin in range(0,len(rows),batch_size):
            chunk=rows[begin:begin+batch_size]
            values=[]
            for row in chunk:
                values.append('('+','.join(_literal(row[col]) for col in source_cols)+')')
            sql=f'-- Reelbrain private research only; expected isolated project xlkdzrhzizuftbnitodr.\n'
            sql+='BEGIN;\n'
            sql+='INSERT INTO reelbrain_research.'+remote+' ('+','.join(target_cols)+') VALUES\n'+',\n'.join(values)+'\nON CONFLICT DO NOTHING;\nCOMMIT;\n'
            counter+=1
            file=dest/f'reelbrain_import_{counter:04d}_{remote}.sql'
            file.write_text(sql,encoding='utf-8')
            files.append(file)
    verification_rows=db.con.execute('''SELECT v.archive_sha,c.catalog_number,v.repo,
       v.github_repository_id,v.checked_at,v.readme_url,
       v.readme_sha AS readme_blob_sha,v.readme_claim AS readme_claims,
       'readme_checked' AS verification_level,v.execution_status
       FROM trend_verifications v JOIN trend_catalog c
       ON v.tenant=c.tenant AND v.archive_sha=c.archive_sha AND v.repo=c.repo
       WHERE v.tenant=? ORDER BY v.archive_sha,v.repo,v.readme_sha''',(tenant,)).fetchall()
    verify_cols=['archive_sha','catalog_number','repo','github_repository_id','checked_at',
                 'readme_url','readme_blob_sha','readme_claims','verification_level','execution_status']
    for begin in range(0,len(verification_rows),batch_size):
        chunk=verification_rows[begin:begin+batch_size]
        values=['('+','.join(_literal(r[c]) for c in verify_cols)+')' for r in chunk]
        sql='-- New private Reelbrain project ONLY; README assertions not runtime verification.\nBEGIN;\n'
        sql+='INSERT INTO reelbrain_research.repository_verifications ('+','.join(verify_cols)+') VALUES\n'+',\n'.join(values)+'\nON CONFLICT DO NOTHING;\nCOMMIT;\n'
        counter+=1
        file=dest/f'reelbrain_import_{counter:04d}_repository_verifications.sql'
        file.write_text(sql,encoding='utf-8')
        files.append(file)
    return files


def record_readme_verification(db:KnowledgeStore, *, tenant:str, repo:str, github_id:str,
                               readme_url:str, readme_sha:str, readme_claim:str) -> dict:
    """Record observed GitHub README snapshot *without running repo code*.

    The claim is a human/reviewer paraphrase of README claims, not independently
    proven functionality, and must NEVER be used to auto-install tool code.
    """
    from urllib.parse import urlsplit
    from .store import digest
    _schema(db)
    _repo(repo)
    if not isinstance(github_id,str) or not github_id.isdecimal():
        raise ValueError('valid GitHub repository metadata ID required')
    if not isinstance(readme_sha,str) or not re.fullmatch(r'[0-9a-f]{40}',readme_sha):
        raise ValueError('readme_sha must be 40-digit Git blob SHA')
    if not isinstance(readme_claim,str) or not (5<=len(readme_claim)<=1500):
        raise ValueError('bounded README research summary required')
    p=urlsplit(readme_url)
    parts=p.path.strip('/').split('/')
    if (p.scheme!='https' or p.netloc!='github.com' or len(parts)<5 or
        '/'.join(parts[:2]).casefold()!=repo.casefold() or parts[2]!='blob' or
        parts[-1] not in ('README.md','README.MD','readme.md') or
        p.query or p.fragment or p.username or p.password):
        raise ValueError('README link must match catalog repository')
    row=db.con.execute('''SELECT archive_sha,repo_url FROM trend_catalog
        WHERE tenant=? AND repo=?''',(tenant,repo)).fetchone()
    if not row:raise ValueError('repo not present in the validated historical catalog')
    checked=utc()
    receipt={'readme_url':readme_url,'readme_blob_sha':readme_sha,
             'github_repository_id':github_id,'reviewed_at':checked,
             'level':'readme_checked','execution_status':'not_tested',
             'notes':'README statements are source claims; no code execution'}
    with db.transaction():
        db.con.execute('''INSERT OR IGNORE INTO trend_verifications
            (tenant,archive_sha,repo,github_repository_id,readme_url,readme_sha,readme_claim,checked_at)
            VALUES(?,?,?,?,?,?,?,?)''',
            (tenant,row['archive_sha'],repo,github_id,readme_url,readme_sha,readme_claim,checked))
        db.con.execute('''UPDATE trend_catalog SET verification_level='readme_checked'
            WHERE tenant=? AND archive_sha=? AND repo=?''',(tenant,row['archive_sha'],repo))
        db.con.execute('''UPDATE resources SET status='readme_checked',verification_receipt=?
            WHERE tenant=? AND canonical_url=? AND status='seen' ''',
            (json.dumps(receipt,sort_keys=True),tenant,row['repo_url']))
    return {'repo':repo,'verification_level':'readme_checked',
            'execution_status':'not_tested','source':readme_url,'sha':readme_sha}
