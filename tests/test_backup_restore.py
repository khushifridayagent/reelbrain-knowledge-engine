"""Offline disaster recovery must be tested without modifying existing systems."""
import os
import tempfile
import unittest
from pathlib import Path
from reelbrain.pipeline import KnowledgePipeline
from reelbrain.store import KnowledgeStore
from reelbrain.backup import backup_database, restore_database, verify_database

class BackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.db=KnowledgeStore(self.root/'primary.sqlite')
        self.tenant='owner'
        KnowledgePipeline(self.db).ingest_report('r.md','Tool https://github.com/example/tool',self.tenant)
        self.raw='See https://instagram.com/reel/Example99/\nExtra notes in Hindi and English'
        KnowledgePipeline(self.db).ingest_reel_conversation('notes.md',self.raw,self.tenant)
    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def test_backup_restores_to_distinct_private_db_with_sources_and_notes(self):
        backup=self.root/'safe'/'backup.sqlite'
        receipt=backup_database(self.db,backup)
        self.assertEqual(receipt['integrity'],'ok')
        self.assertEqual(receipt['source_counts']['sources'],3)
        self.assertTrue(receipt['sha256'])
        restored=self.root/'restored'/'knowledge.sqlite'
        after=restore_database(backup,restored)
        self.assertEqual(after['integrity'],'ok')
        db2=KnowledgeStore(restored)
        try:
            self.assertEqual(db2.counts('owner'),self.db.counts('owner'))
            self.assertEqual(db2.search('tool','owner')[0]['status'],'seen')
            self.assertEqual(len(db2.context_for_reel('https://www.instagram.com/reel/Example99/','owner')),1)
            archive=db2.con.execute("SELECT id FROM sources WHERE kind='conversation_archive'").fetchone()['id']
            self.assertEqual(db2.get_archive_text(archive,'owner'),self.raw)
        finally:db2.close()
        self.assertEqual(verify_database(backup)['integrity'],'ok')
        if os.name=='posix':
            self.assertEqual(backup.stat().st_mode&0o777,0o600)
            self.assertEqual(restored.stat().st_mode&0o777,0o600)

    def test_no_overwrites_existing_backups_or_any_existing_project_files(self):
        backup=self.root/'safe'/'backup.sqlite'
        backup_database(self.db,backup)
        with self.assertRaises(FileExistsError): backup_database(self.db,backup)
        existing=self.root/'important.sqlite'
        existing.write_bytes(b'other-project-content')
        with self.assertRaises(FileExistsError): restore_database(backup,existing)
        self.assertEqual(existing.read_bytes(),b'other-project-content')

    def test_corrupt_backup_refuses_restore_without_leaving_target(self):
        broken=self.root/'corrupt.sqlite';broken.write_bytes(b'NOT A DATABASE')
        target=self.root/'new.sqlite'
        with self.assertRaises(ValueError): restore_database(broken,target)
        self.assertFalse(target.exists())

if __name__=='__main__':unittest.main()
