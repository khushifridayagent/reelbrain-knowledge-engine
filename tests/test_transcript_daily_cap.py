"""Bounded per-day hosted transcript throughput for 0/5/60-Reel bursts."""
import unittest
from unittest.mock import patch


class TranscriptDailyCapTests(unittest.TestCase):
    def test_default_is_two_billable_starts_per_utc_day(self):
        from reelbrain.hosted_transcript_job import daily_transcript_request_cap
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(daily_transcript_request_cap(),2)

    def test_operator_can_allow_sixty_when_budget_approved(self):
        from reelbrain.hosted_transcript_job import daily_transcript_request_cap
        with patch.dict('os.environ',{
            'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
            'REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT':'60',
        },clear=True):
            self.assertEqual(daily_transcript_request_cap(),60)

    def test_unapproved_cannot_expand_daily_spending(self):
        from reelbrain.hosted_transcript_job import daily_transcript_request_cap
        with patch.dict('os.environ',{
            'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'0',
            'REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT':'60'
        },clear=True):
            self.assertEqual(daily_transcript_request_cap(),2)

    def test_reject_unsafe_or_non_numeric_cap(self):
        from reelbrain.hosted_transcript_job import daily_transcript_request_cap
        for raw in ('0','121','nan','hello','-4','3.5'):
            with patch.dict('os.environ',{
                'REELBRAIN_HOSTED_TRANSCRIPT_BUDGET_APPROVED':'1',
                'REELBRAIN_HOSTED_TRANSCRIPT_DAILY_LIMIT':raw,
            },clear=True):
                with self.assertRaises(ValueError):
                    daily_transcript_request_cap()

if __name__=='__main__':unittest.main()
