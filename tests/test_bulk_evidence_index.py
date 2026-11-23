"""Large archives must not invoke URL parsing quadratic times per candidate."""
import unittest
from unittest.mock import patch
import reelbrain.contracts as contract
from reelbrain.contracts import Observation, ResourceCandidate, evidence_filter

class BulkEvidenceTests(unittest.TestCase):
    def test_evidence_filter_index_is_linear_and_preserves_all_citations(self):
        size=100
        observations=[Observation(f'On slide {i}, https://github.com/example/tool-{i}',kind='document',locator=f'L{i}') for i in range(size)]
        candidates=[ResourceCandidate(f'tool-{i}',f'https://github.com/example/tool-{i}') for i in range(size)]
        original=contract.canonical_resource
        with patch('reelbrain.contracts.canonical_resource', wraps=original) as spy:
            verdict=evidence_filter(candidates,observations)
        self.assertEqual(len(verdict.accepted),size)
        self.assertEqual(len(verdict.rejected),0)
        self.assertLess(spy.call_count, size*5,'Quadratic URL validation is too slow for a 2,000+ report archive')
        self.assertEqual(verdict.accepted[24].evidence_ids,(observations[24].uid,))
    def test_inference_never_proves_a_link_even_if_it_matches(self):
        evidence=[Observation('https://github.com/example/tool',kind='model_inference',locator='model')]
        predicted=[ResourceCandidate('tool','https://github.com/example/tool')]
        self.assertEqual(len(evidence_filter(predicted,evidence).accepted),0)
if __name__=='__main__':unittest.main()
