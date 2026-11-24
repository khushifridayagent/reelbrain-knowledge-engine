"""Free hosted vision/ASR quota exhaustion must not permanently finish a Reel."""
import unittest
from reelbrain.model_quota_retry import model_quota_retry_seconds
from reelbrain.batch_outcome import require_successful_batch

class ModelQuotaRetryTests(unittest.TestCase):
    def test_cloudflare_neuron_quota_defers_source_until_daily_capacity_returns(self):
        delay=model_quota_retry_seconds({
            'vlm':"HTTPStatusError: 429 Too Many Requests - daily neuron quota exhausted"})
        self.assertGreaterEqual(delay,3600)
        self.assertLessEqual(delay,86400)

    def test_provider_temporary_outage_defers_without_false_completion(self):
        self.assertIsNotNone(model_quota_retry_seconds({
            'asr':'HTTPStatusError: 503 Service Unavailable'}))

    def test_regular_video_content_and_ocr_errors_are_not_misclassified(self):
        self.assertIsNone(model_quota_retry_seconds({
            'ocr':'ValueError: undecodable carousel page'}))
        self.assertIsNone(model_quota_retry_seconds({
            'vlm':'ValueError: malformed JSON shape'}))
        self.assertIsNone(model_quota_retry_seconds({}))

    def test_model_quota_retry_is_durably_acknowledged_but_github_workflow_stays_red(self):
        outcome={'id':8,'status':'deferred_model_quota','acknowledged_failure':True,
                 'source_url':'https://www.instagram.com/reel/DoNotLeak/'}
        with self.assertRaises(RuntimeError) as raised:
            require_successful_batch([outcome])
        self.assertIn('quota',str(raised.exception).lower())
        self.assertNotIn('DoNotLeak',str(raised.exception))

    def test_unacknowledged_model_retry_never_counts_as_a_success(self):
        with self.assertRaises(RuntimeError) as raised:
            require_successful_batch([
                {'status':'deferred_model_quota','acknowledged_failure':False}])
        self.assertIn('acknowledged',str(raised.exception).lower())

if __name__=='__main__':unittest.main()
