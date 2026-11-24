"""Regression contracts for the sole production media worker."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]/'.github'/'workflows'

class ProductionMediaRouting(unittest.TestCase):
    def test_cobalt_uses_same_eligibility_as_media_dependencies(self):
        workflow=(ROOT/'reelbrain-media-batch.yml').read_text()
        def condition(step):
            block=workflow.split('- name: '+step,1)[1].split('\n      - ',1)[0]
            return next(line.strip() for line in block.splitlines() if line.strip().startswith('if:'))
        self.assertEqual(condition('Start private ephemeral open-source Cobalt'),
                         condition('Install real media tooling'))
        self.assertIn('REELBRAIN_COBALT_READY:',workflow)
    def test_legacy_worker_never_claims_on_push_or_schedule(self):
        workflow=(ROOT/'reelbrain-scheduled-media-worker.yml').read_text()
        triggers=workflow.split('on:',1)[1].split('permissions:',1)[0]
        self.assertNotIn('push:',triggers)
        self.assertNotIn('schedule:',triggers)
        self.assertIn("github.event_name == 'workflow_dispatch'",workflow)
        self.assertIn("vars.REELBRAIN_LEGACY_WORKER_ENABLED == '1'",workflow)
        self.assertIn('group: reelbrain-media-batch',workflow)

if __name__=='__main__':unittest.main()
