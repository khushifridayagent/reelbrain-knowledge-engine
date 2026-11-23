"""Behavioral requirements for grounded, structured historical research import."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from reelbrain.store import KnowledgeStore

ROOT='GitHub_Trending_Two_Year_Intelligence/'


def build_zip(path, *, mismatched_url=False, corrupt_manifest=False):
    catalog=[dict(catalog_number=1,repo='owner/tool-one',repo_url='https://github.com/owner/tool-one',
                  what_it_does='Unverified tool description',core_features='Not independently verified',
                  practical_use_cases='Inspect documentation',evidence='unverified',
                  verification='No official GitHub metadata verification completed.'),
             dict(catalog_number=2,repo='org/tool-two',repo_url='https://github.com/org/tool-two',
                  what_it_does='Not independently verified',core_features='Unknown',
                  practical_use_cases='Evaluate after research',evidence='unverified',
                  verification='No official metadata')]
    if mismatched_url: catalog[1]['repo_url']='https://github.com/other/typosquat'
    files={
        'data/repository_catalog_2406.json':json.dumps(catalog).encode(),
        'data/daily_leaders_731_days.json':json.dumps([dict(date='2026-11-20',primary_rank1=None,primary_rank1_gain=None,primary_gain_repo=None,primary_gain=None,primary_gain_rank=None,secondary_rank1='owner/tool-one',primary_status='not_locally_imported',primary_source='https://example.org/primary',secondary_source='https://example.org/secondary')]).encode(),
        'data/historical_ranked_entries.json':json.dumps([dict(date='2026-11-20',source='secondary_github_archive',rank=1,repo='owner/tool-one',stars_today=None,historic_stars=None,historic_forks=None,archive_description=None,source_url='https://example.org/secondary')]).encode(),
        'data/capture_provenance.json':json.dumps([dict(date='2026-11-20',source='secondary_github_archive',status='ok',captured_at='2026-11-21T00:00:00+00:00',source_url='https://example.org/secondary',content_sha256=None,row_count=1,error='Prior research; no independent verification')]).encode(),
        'data/PROVENANCE_AND_COVERAGE.json':json.dumps(dict(period_start='2026-11-20',period_end='2026-11-20',calendar_days=1,independently_archived_secondary_rank1_days=1,secondary_distinct_identifiers_in_original_catalog=2)).encode(),
    }
    with ZipFile(path,'w',ZIP_DEFLATED) as archive:
        for filename,blob in files.items():archive.writestr(ROOT+filename,blob)
        manifest=''.join(f'{hashlib.sha256(blob).hexdigest()}  {filename}\n' for filename,blob in files.items())
        if corrupt_manifest:manifest=manifest.replace('a','b')
        archive.writestr(ROOT+'FILE_CHECKSUMS_SHA256.txt',manifest)


class TrendingResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'user_research.zip'
        self.db=KnowledgeStore(Path(self.tmp.name)/'private.db')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_import_preserves_all_relations_evidence_and_unverified_status(self):
        from reelbrain.trending_import import import_trending_zip, trending_counts, search_catalog, daily_lookup
        build_zip(self.path)
        result=import_trending_zip(self.path,self.db,tenant='person')
        self.assertEqual(result['catalog_rows'],2)
        self.assertEqual(result['daily_leader_rows'],1)
        self.assertEqual(result['ranked_history_rows'],1)
        self.assertEqual(result['capture_provenance_rows'],1)
        self.assertEqual(result['manifest_files_verified'],5)
        self.assertEqual(self.db.counts('person')['resources'],2)
        self.assertTrue(all(x['status']=='seen' for x in self.db.con.execute('SELECT status FROM resources')))
        self.assertEqual(trending_counts(self.db,'person')['catalog_rows'],2)
        docs=search_catalog(self.db,'tool-one','person')
        self.assertEqual(docs[0]['repo_url'],'https://github.com/owner/tool-one')
        self.assertEqual(docs[0]['verification_level'],'supplied_unverified')
        self.assertTrue(docs[0]['source_locator'].endswith('#/0'))
        self.assertEqual(daily_lookup(self.db,'2026-11-20','person')['secondary_rank1'],'owner/tool-one')
        self.assertTrue(self.db.search('tool-one','person'))
        self.assertEqual(import_trending_zip(self.path,self.db,tenant='person')['catalog_rows'],2)
        self.assertEqual(trending_counts(self.db,'person')['catalog_rows'],2)
        self.assertEqual(self.db.counts('person')['sources'],1)
        self.assertEqual(import_trending_zip(self.path,self.db,tenant='other')['catalog_rows'],2)
        self.assertEqual(trending_counts(self.db,'other')['catalog_rows'],2)
    def test_cli_import_search_and_day_work_without_network(self):
        from reelbrain.cli import run
        from contextlib import redirect_stdout
        import io
        build_zip(self.path)
        db_path=Path(self.tmp.name)/'cli.db'
        def call(*parts):
            sink=io.StringIO()
            with redirect_stdout(sink):code=run(['--db',str(db_path),*parts])
            self.assertEqual(code,0)
            return json.loads(sink.getvalue())
        imported=call('import-trending-zip',str(self.path))
        self.assertEqual(imported['catalog_rows'],2)
        self.assertEqual(call('trending-counts')['catalog_rows'],2)
        self.assertEqual(call('trending-find','tool-one')[0]['repo'],'owner/tool-one')
        self.assertEqual(call('trending-day','2026-11-20')['secondary_rank1'],'owner/tool-one')

    def test_tampered_checksum_has_no_db_side_effects(self):
        from reelbrain.trending_import import import_trending_zip, TrendingImportRejected
        build_zip(self.path,corrupt_manifest=True)
        with self.assertRaises(TrendingImportRejected):import_trending_zip(self.path,self.db)
        self.assertEqual(self.db.counts('personal')['sources'],0)
    def test_rejects_slug_url_mismatch_before_write(self):
        from reelbrain.trending_import import import_trending_zip, TrendingImportRejected
        build_zip(self.path,mismatched_url=True)
        with self.assertRaises(TrendingImportRejected):import_trending_zip(self.path,self.db)
        self.assertEqual(self.db.counts('personal')['sources'],0)
    def test_sql_export_is_non_destructive_and_only_import_tables(self):
        from reelbrain.trending_import import import_trending_zip, export_supabase_sql
        build_zip(self.path); import_trending_zip(self.path,self.db)
        destination=Path(self.tmp.name)/'export'
        paths=export_supabase_sql(self.db,destination,tenant='personal',batch_size=1)
        self.assertGreater(len(paths),1)
        full='\n'.join(p.read_text() for p in paths)
        self.assertIn('reelbrain_research.catalog',full)
        self.assertIn('reelbrain_research.daily_leaders',full)
        self.assertNotIn('DROP ',full.upper())
        self.assertNotIn('TRUNCATE ',full.upper())
        self.assertNotIn('GTA VI',full)
        self.assertIn('supplied_unverified',full)
    def test_case_variant_slug_preserved_without_claiming_distinct_repositories(self):
        from reelbrain.trending_import import import_trending_zip, trending_counts, search_catalog
        build_zip(self.path)
        with ZipFile(self.path) as z:
            payload={i.filename:z.read(i) for i in z.infolist() if not i.is_dir() and not i.filename.endswith('FILE_CHECKSUMS_SHA256.txt')}
        catalog=json.loads(payload[ROOT+'data/repository_catalog_2406.json'])
        catalog[1]['repo']='OWNER/TOOL-ONE';catalog[1]['repo_url']='https://github.com/OWNER/TOOL-ONE'
        payload[ROOT+'data/repository_catalog_2406.json']=json.dumps(catalog).encode()
        with ZipFile(self.path,'w') as z:
            for k,v in payload.items():z.writestr(k,v)
            manifest=''.join(f'{hashlib.sha256(blob).hexdigest()}  {key.removeprefix(ROOT)}\n' for key,blob in payload.items())
            z.writestr(ROOT+'FILE_CHECKSUMS_SHA256.txt',manifest)
        result=import_trending_zip(self.path,self.db)
        self.assertEqual(result['catalog_rows'],2)
        self.assertEqual(result['casefold_identity_collisions'],1)
        self.assertEqual(trending_counts(self.db)['catalog_rows'],2)
        self.assertEqual(len(search_catalog(self.db,'tool-one')),2)

    def test_readme_verification_requires_real_snapshot_receipt(self):
        from reelbrain.trending_import import import_trending_zip, record_readme_verification
        build_zip(self.path);import_trending_zip(self.path,self.db)
        kw=dict(tenant='personal',repo='owner/tool-one',github_id='12345',readme_url='https://github.com/owner/tool-one/blob/main/README.md',
                readme_sha='abcdef0123456789abcdef0123456789abcdef01',
                readme_claim='README claims a sample tool; NOT executed.')
        with self.assertRaises(ValueError):
            record_readme_verification(self.db,**{**kw,'readme_url':'https://github.com/other/typosquat/blob/main/README.md'})
        with self.assertRaises(ValueError):
            record_readme_verification(self.db,**{**kw,'readme_sha':'not-a-sha'})
        self.assertEqual(self.db.con.execute("SELECT status FROM resources WHERE canonical_url='https://github.com/owner/tool-one'").fetchone()[0],'seen')
        rec=record_readme_verification(self.db,**kw)
        self.assertEqual(rec['verification_level'],'readme_checked')
        self.assertEqual(self.db.con.execute("SELECT status FROM resources WHERE canonical_url='https://github.com/owner/tool-one'").fetchone()[0],'readme_checked')
        self.assertEqual(record_readme_verification(self.db,**kw)['verification_level'],'readme_checked')
        self.assertEqual(self.db.con.execute('SELECT count(*) FROM trend_verifications').fetchone()[0],1)
        from reelbrain.trending_import import search_catalog
        results=search_catalog(self.db,'sample tool')
        self.assertEqual(len(results),1)
        self.assertEqual(results[0]['verification_level'],'readme_checked')
        self.assertIn('NOT executed',results[0]['readme_claim'])
        from reelbrain.trending_import import export_supabase_sql
        sql_files=export_supabase_sql(self.db,Path(self.tmp.name)/'receipt_export',batch_size=1)
        sql='\n'.join(p.read_text() for p in sql_files)
        self.assertIn('reelbrain_research.repository_verifications',sql)
        self.assertIn(kw['readme_sha'],sql)

    def test_disallows_invalid_history_date(self):
        from reelbrain.trending_import import import_trending_zip, TrendingImportRejected
        build_zip(self.path)
        with ZipFile(self.path) as z:
            content={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
        hist=json.loads(content[ROOT+'data/historical_ranked_entries.json'])
        hist[0]['date']='not a date'
        content[ROOT+'data/historical_ranked_entries.json']=json.dumps(hist).encode()
        with ZipFile(self.path,'w') as z:
            for k,v in content.items():z.writestr(k,v)
        with self.assertRaises(TrendingImportRejected):import_trending_zip(self.path,self.db)
        self.assertEqual(self.db.counts('personal')['sources'],0)
