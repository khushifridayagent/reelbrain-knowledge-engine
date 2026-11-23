import tempfile,unittest,zipfile
from pathlib import Path
from reelbrain.store import KnowledgeStore
from reelbrain.pipeline import KnowledgePipeline

class ArchiveResearchTests(unittest.TestCase):
    def setUp(self):
        self.d=tempfile.TemporaryDirectory();self.zip=Path(self.d.name)/'big.zip'
        self.db=KnowledgeStore(Path(self.d.name)/'db.sqlite')
    def tearDown(self):self.db.close();self.d.cleanup()
    def test_zip_import_research_and_dedup_without_disk_extraction(self):
        from reelbrain.archive import import_research_zip
        with zipfile.ZipFile(self.zip,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('2026/GitHub Weekly.md','Onyx https://github.com/onyx-dot-app/onyx\n\nMore tools')
            z.writestr('2025/Repos.csv','url,notes\nhttps://github.com/pgvector/pgvector,Vector search')
            z.writestr('README.exe','malware placeholder')
        stats=import_research_zip(self.zip,KnowledgePipeline(self.db),tenant='alone')
        self.assertEqual(stats['imported_documents'],2)
        self.assertEqual(stats['resource_mentions'],2)
        self.assertEqual(self.db.counts('alone')['resources'],2)
        stats2=import_research_zip(self.zip,KnowledgePipeline(self.db),tenant='alone')
        self.assertEqual(stats2['imported_documents'],2)
        self.assertEqual(self.db.counts('alone')['sources'],2)
    def test_zip_path_traversal_rejected(self):
        from reelbrain.archive import import_research_zip,ArchiveRejected
        with zipfile.ZipFile(self.zip,'w') as z:z.writestr('../hidden.md','bad')
        with self.assertRaises(ArchiveRejected):import_research_zip(self.zip,KnowledgePipeline(self.db),tenant='alone')
        self.assertEqual(self.db.counts('alone')['sources'],0)
    def test_zip_single_member_budget_checked_before_ingest(self):
        from reelbrain.archive import import_research_zip,ArchiveRejected
        with zipfile.ZipFile(self.zip,'w') as z:z.writestr('large.md','X'*3000)
        with self.assertRaises(ArchiveRejected):import_research_zip(self.zip,KnowledgePipeline(self.db),tenant='alone',max_member_bytes=1024)
        self.assertEqual(self.db.counts('alone')['sources'],0)
