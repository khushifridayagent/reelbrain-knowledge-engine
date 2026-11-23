"""Indexed FTS5 search of user-supplied historical research.

Never promotes claims to verified facts. Local SQLite only. FTS index is populated
on explicit first search against the selected database and maintained by triggers.
"""
from __future__ import annotations
import re
import sqlite3
from .store import KnowledgeStore
from .trending_import import _schema, search_catalog

# SQL identifiers below are all constants. User queries are only bound parameters.
_QUERY_WORDS = re.compile(r'[^\W_]+', re.UNICODE)
_CREATE_FTS = '''CREATE VIRTUAL TABLE IF NOT EXISTS trend_catalog_fts USING fts5(
 tenant UNINDEXED, archive_sha UNINDEXED, catalog_number UNINDEXED,
 repo,repo_url,what_it_does,core_features,practical_use_cases,evidence,
 tokenize='unicode61 remove_diacritics 2')'''


class FastCatalogSearch:
    def __init__(self, db:KnowledgeStore):
        self.db=db
        self.index_ready=False

    def ensure_index(self)->None:
        if self.index_ready:return
        _schema(self.db)
        con=self.db.con
        con.execute(_CREATE_FTS)
        con.executescript('''
        CREATE TRIGGER IF NOT EXISTS catalog_fastsearch_insert AFTER INSERT ON trend_catalog BEGIN
          INSERT INTO trend_catalog_fts(tenant,archive_sha,catalog_number,repo,repo_url,what_it_does,core_features,practical_use_cases,evidence)
          VALUES(new.tenant,new.archive_sha,new.catalog_number,new.repo,new.repo_url,new.what_it_does,new.core_features,new.practical_use_cases,new.evidence);
        END;
        CREATE TRIGGER IF NOT EXISTS catalog_fastsearch_delete AFTER DELETE ON trend_catalog BEGIN
          DELETE FROM trend_catalog_fts WHERE tenant=old.tenant AND archive_sha=old.archive_sha AND catalog_number=old.catalog_number;
        END;
        CREATE TRIGGER IF NOT EXISTS catalog_fastsearch_update AFTER UPDATE ON trend_catalog BEGIN
          DELETE FROM trend_catalog_fts WHERE tenant=old.tenant AND archive_sha=old.archive_sha AND catalog_number=old.catalog_number;
          INSERT INTO trend_catalog_fts(tenant,archive_sha,catalog_number,repo,repo_url,what_it_does,core_features,practical_use_cases,evidence)
          VALUES(new.tenant,new.archive_sha,new.catalog_number,new.repo,new.repo_url,new.what_it_does,new.core_features,new.practical_use_cases,new.evidence);
        END;
        ''')
        # Idempotent rebuild when this database was populated before index setup.
        # FTS is derivative and may be safely regenerated; canonical catalog is never modified.
        catalog_count=con.execute('SELECT count(*) FROM trend_catalog').fetchone()[0]
        index_count=con.execute('SELECT count(*) FROM trend_catalog_fts').fetchone()[0]
        if index_count!=catalog_count:
            with self.db.transaction():
                con.execute('DELETE FROM trend_catalog_fts')
                con.execute('''INSERT INTO trend_catalog_fts
                (tenant,archive_sha,catalog_number,repo,repo_url,what_it_does,core_features,practical_use_cases,evidence)
                SELECT tenant,archive_sha,catalog_number,repo,repo_url,what_it_does,core_features,practical_use_cases,evidence FROM trend_catalog''')
        self.index_ready=True

    def search(self,query:str,tenant:str='personal',limit:int=20)->list[dict]:
        q=query.strip()[:180]
        if not q:return []
        if not 1<=limit<=100:raise ValueError('limit must be 1..100')
        self.ensure_index()
        tokens=list(dict.fromkeys(s.lower() for s in _QUERY_WORDS.findall(q) if len(s)>=2))[:10]
        if not tokens:return []
        # No raw FTS query ever enters SQL; quote and bound each token to prevent syntax injection.
        match_query=' AND '.join('"'+s.replace('"','""')+'"' for s in tokens)
        sql='''SELECT c.repo,c.repo_url,c.what_it_does,c.core_features,c.practical_use_cases,
                 c.evidence,c.source_verification,c.verification_level,c.source_locator,c.archive_sha,
                 (SELECT v.readme_claim FROM trend_verifications v
                    WHERE v.tenant=c.tenant AND v.archive_sha=c.archive_sha AND v.repo=c.repo
                    ORDER BY v.checked_at DESC LIMIT 1) AS readme_claim,
                 bm25(trend_catalog_fts,5.0,3.0,1.0,1.0,1.0,0.3) AS search_rank
           FROM trend_catalog_fts JOIN trend_catalog c
             ON c.tenant=trend_catalog_fts.tenant
             AND c.archive_sha=trend_catalog_fts.archive_sha
             AND c.catalog_number=trend_catalog_fts.catalog_number
           WHERE trend_catalog_fts MATCH ? AND c.tenant=?
           ORDER BY CASE WHEN lower(c.repo)=lower(?) THEN 0 ELSE 1 END,
             search_rank ASC,c.repo ASC LIMIT ?'''
        rows=[dict(r) for r in self.db.con.execute(sql,(match_query,tenant,q,limit)).fetchall()]
        if not rows:
            # Substring fallback for dashed package names and partial terms.
            rows=search_catalog(self.db,q,tenant,limit)
            for row in rows:row['search_rank']=None
        return rows
