"""Regression cases for simultaneous failures and durable queue invariants."""
import unittest

from reelbrain.resumable_media import classify_partial, retry_seconds
from reelbrain.queue_health import evaluate_health
from reelbrain.batch_outcome import require_successful_batch


class FailureInvariantTests(unittest.TestCase):
    def test_quota_must_not_mask_unrelated_required_stage_failure(self):
        for errors in (
            {'ocr':'focused decoder or checkpoint failed','vlm':'quota exceeded'},
            {'asr':'speech extraction unavailable','vlm':'hybrid provider cooldown:1800'},
            {'vlm':'quota exceeded','completion_evidence':'required modality not attempted'},
        ):
            with self.subTest(errors=errors):
                self.assertEqual(classify_partial(errors),'deferred_incomplete')

    def test_known_coverage_yield_with_quota_still_resumes(self):
        self.assertEqual(classify_partial({'ocr':'focused coverage pending: time budget',
                                          'vlm':'hybrid provider cooldown:1800'}),'deferred_model_quota')
        self.assertEqual(retry_seconds({'ocr':'focused coverage pending: time budget',
                                        'vlm':'hybrid provider cooldown:1800'}),1800)

    def test_unresolved_required_stage_is_not_masked_by_other_completed_jobs(self):
        with self.assertRaisesRegex(RuntimeError,'incomplete'):
            require_successful_batch([{'status':'evidence_saved'},
                {'status':'deferred_incomplete','acknowledged_failure':True}])

    def test_watchdog_detects_invariant_violations_even_with_recent_success(self):
        healthy={'pending':5,'old_pending':4,'recent_completed':3,
                 'stale_leases':0,'dead_letters':0}
        for key,alert in (
            ('exhausted_queued','exhausted_queued'),
            ('invalid_leases','invalid_lease'),
            ('missing_availability','missing_availability'),
            ('processed_without_completion','completion_mismatch'),
            ('unresolved_incomplete','unresolved_required_stage'),
            ('overdue_untouched','queue_starvation'),
        ):
            with self.subTest(key=key):
                self.assertIn(alert,evaluate_health({**healthy,key:1}))

    def test_new_metrics_must_not_accept_negative_or_boolean_values(self):
        healthy={'pending':5,'old_pending':4,'recent_completed':3,
                 'stale_leases':0,'dead_letters':0}
        for value in (-1,True,None):
            with self.assertRaises(ValueError):
                evaluate_health({**healthy,'exhausted_queued':value})
