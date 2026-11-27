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

    def test_mixed_durable_progress_and_deferrals_are_not_total_failure(self):
        # Exact incident shape: two persisted media results plus two safe deferrals.
        results = [{'status': 'deferred_access', 'acknowledged_failure': True},
                   {'status': 'evidence_saved'}, {'status': 'evidence_saved'},
                   {'status': 'deferred_progress', 'acknowledged_failure': True}]
        require_successful_batch(results)
        require_successful_batch(list(reversed(results)))

    def test_mixed_batch_still_fails_on_hard_or_unacknowledged_failure(self):
        for failure in ({'status': 'retry_or_dead_letter', 'acknowledged_failure': True},
                        {'status': 'deferred_access', 'acknowledged_failure': False},
                        {'status': 'deferred_progress', 'acknowledged_failure': False},
                        {'status': 'unknown'}):
            with self.subTest(failure=failure):
                with self.assertRaises(RuntimeError):
                    require_successful_batch([{'status': 'evidence_saved'}, failure])

    def test_all_access_or_quota_deferrals_remain_unsuccessful(self):
        for status in ('deferred_access', 'deferred_model_quota'):
            with self.subTest(status=status):
                with self.assertRaises(RuntimeError):
                    require_successful_batch([{'status': status, 'acknowledged_failure': True}])

    def test_all_durably_deferred_batches_are_operational_not_completed(self):
        from contextlib import redirect_stdout
        import io
        for statuses in (['deferred_model_quota']*4,
                         ['deferred_access']*4,
                         ['deferred_model_quota','deferred_access','deferred_progress'],
                         ['deferred_progress']):
            with self.subTest(statuses=statuses), redirect_stdout(io.StringIO()) as output:
                summary=require_successful_batch([
                    {'status':status,'acknowledged_failure':True} for status in statuses])
                self.assertEqual(summary['state'],'deferred')
                self.assertEqual(summary['completed'],0)
                self.assertEqual(summary['deferred'],len(statuses))
                self.assertIn('::warning::',output.getvalue())
                self.assertNotIn('successfully completed',output.getvalue())

    def test_safe_deferrals_never_hide_hard_or_unacknowledged_failure(self):
        for status in ('deferred_access','deferred_model_quota','deferred_progress','deferred_incomplete'):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                require_successful_batch([{'status':'deferred_model_quota','acknowledged_failure':True},
                                          {'status':status,'acknowledged_failure':False}])
        with self.assertRaises(RuntimeError):
            require_successful_batch([{'status':'deferred_access','acknowledged_failure':True},
                                      {'status':'retry_or_dead_letter','acknowledged_failure':True}])

    def test_unknown_result_status_is_not_treated_as_success(self):
        with self.assertRaises(RuntimeError):
            require_successful_batch([{'status': 'secretly_failed'}])


if __name__ == '__main__':
    unittest.main()
