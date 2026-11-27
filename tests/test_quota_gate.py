"""Regression tests for quota admission; no real media, keys or network."""
import sqlite3
import unittest
from unittest.mock import Mock, patch
from reelbrain.quota_gate import (
    configured_vision_keys, all_vision_blocked_seconds, QUOTA_WAIT_FILTER,
    claim_media_jobs,
)


class QuotaGateTests(unittest.TestCase):
    def test_only_explicitly_configured_providers_count(self):
        with patch.dict('os.environ', {'REELBRAIN_NATIVE_HYBRID_ENABLED':'1',
                                       'GEMINI_API_KEY':'fixture'}, clear=True):
            self.assertEqual(configured_vision_keys(), ('gemini_vision',))
        with patch.dict('os.environ', {'GEMINI_API_KEY':'fixture'}, clear=True):
            self.assertEqual(configured_vision_keys(), ())

    def test_wait_only_when_every_configured_provider_is_blocked(self):
        cur=Mock()
        keys=('gemini_vision','groq_vision','cloudflare_vision')
        cur.fetchall.return_value=[('gemini_vision',400),('groq_vision',800),('cloudflare_vision',3600)]
        self.assertEqual(all_vision_blocked_seconds(cur,keys),400)
        cur.fetchall.return_value=[('gemini_vision',400),('cloudflare_vision',3600)]
        self.assertEqual(all_vision_blocked_seconds(cur,keys),0)
        cur.fetchall.return_value=[('gemini_vision',400),('groq_vision',0),('cloudflare_vision',3600)]
        self.assertEqual(all_vision_blocked_seconds(cur,keys),0)
        cur.reset_mock()
        self.assertEqual(all_vision_blocked_seconds(cur,()),0)
        cur.execute.assert_not_called()

    def test_only_previously_quota_deferred_rows_are_held(self):
        with sqlite3.connect(':memory:') as db:
            db.execute('create table jobs(id int,status text,last_error text)')
            db.executemany('insert into jobs values(?,?,?)',[
                (1,'queued','Model quota temporarily unavailable'),
                (2,'queued',None),
                (3,'queued','Media coverage pending; resume saved checkpoints'),
                (4,'queued','Public media unavailable'),
                (5,'leased','Model quota temporarily unavailable'),
            ])
            self.assertEqual(db.execute('select id from jobs where '+QUOTA_WAIT_FILTER+' order by id').fetchall(),
                             [(2,),(3,),(4,),(5,)])

    def test_normal_claim_path_unchanged_when_any_provider_available(self):
        cur=Mock()
        claim_media_jobs(cur,1,0)
        self.assertIn('reelbrain_claim_dm_jobs',cur.execute.call_args.args[0])
        self.assertEqual(cur.execute.call_args.args[1],(1,900))

    def test_cooldown_claim_remains_atomic_and_skips_only_quota_jobs(self):
        cur=Mock()
        claim_media_jobs(cur,4,400)
        sql,args=cur.execute.call_args.args
        self.assertIn(QUOTA_WAIT_FILTER,sql)
        self.assertIn('for update skip locked',sql.lower())
        self.assertIn('attempts=j.attempts+1',sql)
        self.assertEqual(args,(4,))
