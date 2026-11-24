"""External Instagram access failures must not exhaust or silently discard six queued Reels."""
import unittest
from unittest.mock import patch

from reelbrain.public_media import PublicMediaError


class Connection:
    def __init__(self):
        self.sql=[]
        self.commits=0
        self.rollbacks=0
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def cursor(self):return Cursor(self)
    def commit(self):self.commits+=1
    def rollback(self):self.rollbacks+=1


class Cursor:
    def __init__(self,con):self.con=con
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def execute(self,sql,args=()):self.con.sql.append((sql,args))
    def fetchall(self):return [(5,'https://www.instagram.com/reel/EXAMPLE1/','fake-lease-token')]
    def fetchone(self):return (True,)


class AccessDeferralTests(unittest.TestCase):
    def test_rate_limit_waits_longer_than_extractor_failure(self):
        from reelbrain.access_backoff import access_backoff_seconds
        a=access_backoff_seconds(PublicMediaError('Public media unavailable: gallery_rate_limited'))
        b=access_backoff_seconds(PublicMediaError('Public media unavailable: gallery_unavailable'))
        self.assertGreaterEqual(a,3600)
        self.assertGreater(a,b)
    def test_access_failure_stays_recoverable_instead_of_dead_letter(self):
        from reelbrain.durable_worker import run_one_batch
        conn=Connection()
        def fail(*args):
            raise PublicMediaError('Public media unavailable: gallery_http_forbidden')
        with patch('reelbrain.durable_worker.pg_open',return_value=conn):
            result=run_one_batch({'db_url':'fixture://', 'apify_token':'', 'acquisition':'yt_dlp_public'},
                                 batch_size=1,processor=fail)
        self.assertEqual(result[0]['status'],'deferred_access')
        self.assertTrue(result[0]['acknowledged_failure'])
        sql='\n'.join(q for q,_ in conn.sql)
        self.assertIn('reelbrain_defer_dm_job',sql)
        self.assertNotIn('reelbrain_fail_dm_job',sql)
        self.assertGreater(conn.commits,0)
    def test_real_software_error_uses_bounded_dead_letter_retry(self):
        from reelbrain.durable_worker import run_one_batch
        conn=Connection()
        def bug(*args):
            raise RuntimeError('unexpected code bug')
        with patch('reelbrain.durable_worker.pg_open',return_value=conn):
            result=run_one_batch({'db_url':'fixture://', 'apify_token':'', 'acquisition':'yt_dlp_public'},
                                 batch_size=1,processor=bug)
        self.assertEqual(result[0]['status'],'retry_or_dead_letter')
        sql='\n'.join(q for q,_ in conn.sql)
        self.assertIn('reelbrain_fail_dm_job',sql)
        self.assertNotIn('reelbrain_defer_dm_job',sql)

if __name__ == '__main__':
    unittest.main()
