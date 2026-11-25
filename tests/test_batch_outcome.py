"""Batch exit status must reflect actual media outcomes, not only an HTTP 200."""
import unittest

from reelbrain.batch_outcome import require_successful_batch


class BatchOutcomeTests(unittest.TestCase):
    def test_idle_and_success_are_clean(self):
        for outcomes in ([], [{'status': 'evidence_saved'}],
                         [{'status': 'partial'}], [{'status': 'processed'}]):
            with self.subTest(outcomes=outcomes):
                require_successful_batch(outcomes)

    def test_acknowledged_media_failure_must_fail_workflow(self):
        outcomes = [{'status': 'retry_or_dead_letter',
                     'acknowledged_failure': True,
                     'source_url': 'https://www.instagram.com/reel/PRIVATE_URL/'}]
        with self.assertRaises(RuntimeError) as raised:
            require_successful_batch(outcomes)
        self.assertIn('retry', str(raised.exception).lower())
        self.assertNotIn('PRIVATE_URL', str(raised.exception))

    def test_unacknowledged_queue_failure_is_fatal(self):
        with self.assertRaises(RuntimeError) as raised:
            require_successful_batch([{'status': 'retry_or_dead_letter',
                                       'acknowledged_failure': False}])
        self.assertIn('acknowledged', str(raised.exception).lower())

    def test_progress_and_incomplete_have_truthful_errors(self):
        for status,phrase in [('deferred_progress','coverage'),('deferred_incomplete','incomplete')]:
            with self.subTest(status=status):
                with self.assertRaises(RuntimeError) as raised:
                    require_successful_batch([{'status':status,'acknowledged_failure':True}])
                self.assertIn(phrase,str(raised.exception).lower())
                self.assertNotIn('quota',str(raised.exception).lower())

    def test_unknown_result_status_is_not_treated_as_success(self):
        with self.assertRaises(RuntimeError):
            require_successful_batch([{'status': 'secretly_failed'}])


if __name__ == '__main__':
    unittest.main()
