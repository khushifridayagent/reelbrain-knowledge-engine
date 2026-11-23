"""Regression specs for chronology-preserving Reel conversation imports."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reelbrain.pipeline import KnowledgePipeline
from reelbrain.store import KnowledgeStore
from reelbrain.sources import extract_instagram_mentions
from reelbrain.cli import run


class ReelConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = KnowledgeStore(self.root / 'reels.db')
        self.pipe = KnowledgePipeline(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_mention_provenance_preserves_all_occurrences_and_urls(self):
        txt = ('First note about GPU search.\n'
               'https://instagram.com/reel/AbC123/?igsh=foo\n'
               'Second link: https://www.instagram.com/p/Car01/\n'
               'See again https://instagram.com/reel/AbC123/\n')
        mentions = extract_instagram_mentions(txt)
        self.assertEqual([m.line for m in mentions], [2, 3, 4])
        self.assertEqual([m.canonical_url for m in mentions],
                         ['https://www.instagram.com/reel/AbC123/',
                          'https://www.instagram.com/p/Car01/',
                          'https://www.instagram.com/reel/AbC123/'])
        self.assertTrue(all(m.char_offset >= 0 for m in mentions))
        self.assertIn('First note', mentions[0].context)

    def test_original_conversation_archived_with_precise_mentions_but_not_as_reel_evidence(self):
        text = ('I think this makes on-screen apps easier.\n'
                'https://www.instagram.com/reel/CODE_one/\n'
                'Creator says github.com/not-checked/tool, but I have not opened the Reel.\n'
                'Another one https://www.instagram.com/reel/CODE_two/\n')
        result = self.pipe.ingest_reel_conversation('reels_chat.md', text, 'alice')
        self.assertEqual(result['unique_urls'], 2)
        self.assertEqual(result['mentions'], 2)
        self.assertEqual(result['queued_jobs'], 2)
        self.assertEqual(self.store.counts('alice')['resources'], 0)  # NO false repo verified in reel.
        self.assertEqual(self.store.get_archive_text(result['archive_source_id'], 'alice'), text)
        context = self.store.context_for_reel('https://www.instagram.com/reel/CODE_one/', 'alice')
        self.assertEqual(len(context), 1)
        self.assertIn('reels_chat.md:L2', context[0]['locator'])
        self.assertIn('I think', context[0]['context'])
        self.assertEqual(context[0]['provenance'], 'user_provided_note_not_reel_evidence')
        self.assertEqual(self.store.search('not-checked', 'alice'), [])

    def test_idempotent_reimport_does_not_mutate_existing_information(self):
        content = 'https://instagram.com/reel/abc1/\n' * 3
        first = self.pipe.ingest_reel_conversation('same.txt', content, 'person')
        second = self.pipe.ingest_reel_conversation('same.txt', content, 'person')
        self.assertEqual(first['archive_source_id'], second['archive_source_id'])
        self.assertEqual(self.store.counts('person')['sources'], 2)  # 1 archive + 1 link-only reel
        self.assertEqual(self.store.counts('person')['jobs'], 1)
        self.assertEqual(len(self.store.context_for_reel('https://instagram.com/reel/abc1/', 'person')), 3)

    def test_edits_are_versioned_without_overwriting_old_source(self):
        first = self.pipe.ingest_reel_conversation('notes.md', 'https://instagram.com/reel/alpha/', 'A')
        second = self.pipe.ingest_reel_conversation('notes.md', 'https://instagram.com/reel/alpha/\nextra insight', 'A')
        self.assertNotEqual(first['archive_source_id'], second['archive_source_id'])
        self.assertEqual(self.store.get_archive_text(first['archive_source_id'], 'A'),
                         'https://instagram.com/reel/alpha/')
        self.assertEqual(len(self.store.context_for_reel('https://instagram.com/reel/alpha/','A')), 2)

    def test_import_does_not_cross_tenant_boundary(self):
        r = self.pipe.ingest_reel_conversation('private.md','https://instagram.com/reel/private1/','owner')
        self.assertIsNone(self.store.get_archive_text(r['archive_source_id'],'someone_else'))
        self.assertEqual(self.store.context_for_reel('https://instagram.com/reel/private1/','someone_else'), [])

    def test_empty_input_preserved_but_no_fabricated_reel(self):
        r=self.pipe.ingest_reel_conversation('empty.md','Only ordinary text about research.', 'owner')
        self.assertEqual(r['mentions'], 0)
        self.assertEqual(r['queued_jobs'], 0)
        self.assertEqual(self.store.get_archive_text(r['archive_source_id'],'owner'), 'Only ordinary text about research.')

    def test_existing_import_reels_text_cli_uses_new_context_preserving_path(self):
        raw='Context from user about research\nhttps://instagram.com/reel/ReelXyz/\n'
        p=self.root/'chat.txt';p.write_text(raw)
        with patch('builtins.print') as printer:
            self.assertEqual(run(['--db', str(self.root/'cli.db'), '--tenant','owner','import-reels-text',str(p)]), 0)
        output=json.loads(printer.call_args.args[0])
        self.assertEqual(output['unique_urls'],1)
        db=KnowledgeStore(self.root/'cli.db')
        try:
            self.assertEqual(len(db.context_for_reel('https://instagram.com/reel/ReelXyz/','owner')),1)
            self.assertEqual(db.get_archive_text(output['archive_source_id'],'owner'),raw)
        finally: db.close()

    def test_invalid_archive_over_budget_rejected_before_write(self):
        with self.assertRaises(ValueError):
            self.pipe.ingest_reel_conversation('too_big.md','abc'*100,max_text_bytes=10)
        self.assertEqual(self.store.counts('personal')['sources'],0)

if __name__=='__main__': unittest.main()
