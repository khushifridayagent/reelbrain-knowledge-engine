import unittest
from reelbrain.queue_health import evaluate_health

class QueueHealthTests(unittest.TestCase):
    def test_idle_and_recent_progress_are_healthy(self):
        for row in ({'pending':0,'old_pending':0,'recent_completed':0,'stale_leases':0,'dead_letters':0},
                    {'pending':200,'old_pending':200,'recent_completed':1,'stale_leases':0,'dead_letters':0}):
            self.assertEqual(evaluate_health(row),[])

    def test_short_outage_does_not_alert(self):
        self.assertEqual(evaluate_health({'pending':10,'old_pending':0,'recent_completed':0,
                                         'stale_leases':0,'dead_letters':0}),[])

    def test_sustained_stall_is_not_hidden_by_safe_deferrals(self):
        row={'pending':100,'old_pending':98,'recent_completed':0,'stale_leases':0,'dead_letters':0}
        self.assertIn('completion_stalled',evaluate_health(row))

    def test_expired_leases_and_dead_letters_are_independent_alerts(self):
        row={'pending':1,'old_pending':0,'recent_completed':10,'stale_leases':1,'dead_letters':1}
        self.assertEqual(set(evaluate_health(row)),{'stale_lease','dead_letter'})

    def test_invalid_metrics_fail_closed(self):
        for row in ({}, {'pending':-1,'old_pending':0,'recent_completed':0,'stale_leases':0,'dead_letters':0}):
            with self.assertRaises(ValueError): evaluate_health(row)
