"""Phase 7 — test-first requirements: fast searchable catalog and isolation."""
import tempfile, unittest
from pathlib import Path
from reelbrain.store import KnowledgeStore
from reelbrain.fastsearch import FastCatalogSearch

class FastSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=KnowledgeStore(Path(self.tmp.name)/'data.db')
        from reelbrain.trending_import import _schema
        _schema(self.db)
        self.db.con.execute("INSERT INTO trend_archives (tenant, archive_sha, archive_name, source_id, coverage_json, verified_manifest_count, imported_at) VALUES ('u1','abc','archive.zip','source','{}',1,'2026-11-23')")
        self.db.con.execute("INSERT INTO trend_archives (tenant, archive_sha, archive_name, source_id, coverage_json, verified_manifest_count, imported_at) VALUES ('u2','abc','archive.zip','source','{}',1,'2026-11-23')")
        self.db.con.execute("""INSERT INTO trend_catalog(tenant,archive_sha,repo,catalog_number,repo_url,what_it_does,core_features,practical_use_cases,evidence,source_verification,verification_level,source_locator)
          VALUES ('u1','abc','onyx-dot-app/onyx',1,'https://github.com/onyx-dot-app/onyx','Self-hosted research search','agentic RAG retrieval','knowledge assistant','unverified','not_checked','supplied_unverified','archive.zip#/1'),
                 ('u1','abc','someone/runner',2,'https://github.com/someone/runner','Fast workflow automation','agents and scheduling','automation tasks','unverified','not_checked','supplied_unverified','archive.zip#/2'),
                 ('u2','abc','private/acme',1,'https://github.com/private/acme','special agentic rag','secrets','never expose','unverified','not_checked','supplied_unverified','archive.zip#/3')""")
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_catalog_search_ranked_and_provenance_preserved(self):
        hits=FastCatalogSearch(self.db).search('agentic RAG','u1')
        self.assertEqual(hits[0]['repo'],'onyx-dot-app/onyx')
        self.assertEqual(hits[0]['verification_level'],'supplied_unverified')
        self.assertIn('archive.zip',hits[0]['source_locator'])
    def test_query_isolation_and_sql_literal_escaping(self):
        search=FastCatalogSearch(self.db)
        self.assertEqual(search.search('special agentic','u1'),[])
        self.assertEqual(search.search('" OR 1=1 --','u1'),[])
        self.assertEqual(len(search.search('agentic','u2')),1)
    def test_fts_automatically_tracks_new_insert(self):
        search=FastCatalogSearch(self.db)
        search.search('automation','u1')
        self.db.con.execute("""INSERT INTO trend_catalog(tenant,archive_sha,repo,catalog_number,repo_url,what_it_does,core_features,practical_use_cases,evidence,source_verification,verification_level,source_locator)
          VALUES ('u1','abc','future/new',3,'https://github.com/future/new','Quantum retrieval index','very rare specialword13','testing','unverified','not_checked','supplied_unverified','x#/3')""")
        self.assertEqual(search.search('specialword13','u1')[0]['repo'],'future/new')
    def test_multiword_and_exact_repo_priority(self):
        search=FastCatalogSearch(self.db)
        self.assertEqual(search.search('onyx-dot-app/onyx','u1')[0]['repo'],'onyx-dot-app/onyx')
        self.assertEqual(search.search('workflow automation','u1')[0]['repo'],'someone/runner')
