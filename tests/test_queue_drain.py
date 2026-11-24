"""Bounded unattended queue draining: no duplicate claims, no empty-loop churn."""
import unittest
from reelbrain.queue_drain import drain_ready_queue


class QueueDrainTests(unittest.TestCase):
    def test_drains_multiple_jobs_and_stops_as_soon_as_empty(self):
        calls=[]
        outputs=[
            [{'id':5,'status':'processed'}],
            [{'id':6,'status':'partial'}],
            [],
        ]
        def run(config,batch_size=1):
            calls.append(batch_size)
            return outputs.pop(0)
        result=drain_ready_queue({'db_url':'private'},
                                 process_batch=run,max_jobs=6,
                                 time_remaining=lambda:600)
        self.assertEqual([x['id'] for x in result],[5,6])
        self.assertEqual(calls,[1,1,1])

    def test_deferred_instagram_job_does_not_block_another_ready_job(self):
        outputs=[
            [{'id':7,'status':'deferred_access','acknowledged_failure':True}],
            [{'id':8,'status':'processed'}],[],
        ]
        def run(config,batch_size=1):return outputs.pop(0)
        result=drain_ready_queue({},process_batch=run,max_jobs=6,
                                  time_remaining=lambda:600)
        self.assertEqual(len(result),2)
        self.assertEqual(result[1]['status'],'processed')

    def test_budget_and_max_jobs_are_respected(self):
        calls=[]
        def run(config,batch_size=1):
            calls.append(1)
            return [{'id':len(calls),'status':'processed'}]
        result=drain_ready_queue({},process_batch=run,max_jobs=3,
                                  time_remaining=lambda:600)
        self.assertEqual(len(result),3)
        self.assertEqual(len(calls),3)
        calls.clear()
        self.assertEqual(drain_ready_queue({},process_batch=run,
                                           time_remaining=lambda:120),[])
        self.assertFalse(calls)

    def test_unacknowledged_queue_failure_never_gets_silently_skipped(self):
        calls=[]
        def run(config,batch_size=1):
            calls.append(1)
            return [{'id':5,'status':'retry_or_dead_letter','acknowledged_failure':False}]
        with self.assertRaises(RuntimeError):
            drain_ready_queue({},process_batch=run,time_remaining=lambda:600)
        self.assertEqual(len(calls),1)

    def test_reject_invalid_budgets(self):
        with self.assertRaises(ValueError):
            drain_ready_queue({},max_jobs=0)
        with self.assertRaises(ValueError):
            drain_ready_queue({},max_jobs=20)


if __name__=='__main__': unittest.main()
