"""Cost guard: idle queue must skip expensive media stack setup."""
import unittest
from pathlib import Path


class WorkflowCostGuardTests(unittest.TestCase):
    def test_idle_queue_skips_heavy_dependencies_and_media_processing(self):
        path=Path(__file__).resolve().parents[1]/'.github/workflows/reelbrain-media-batch.yml'
        content=path.read_text(encoding='utf-8')
        self.assertIn('id: queue_check',content)
        self.assertIn('eligible_jobs',content)
        self.assertIn('steps.queue_check.outputs.has_jobs',content)
        self.assertGreaterEqual(content.count("steps.queue_check.outputs.has_jobs == 'true'"),4)


if __name__ == '__main__':
    unittest.main()
