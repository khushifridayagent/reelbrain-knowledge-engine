"""Free hosted vision/ASR quota exhaustion must not permanently finish a Reel."""
import unittest
from datetime import datetime,timezone
from reelbrain.model_quota_retry import model_quota_retry_seconds
from reelbrain.batch_outcome import require_successful_batch

class ModelQuotaRetryTests(unittest.TestCase):
    def test_cloudflare_neuron_quota_defers_source_until_daily_capacity_returns(self):
        delay=model_quota_retry_seconds({
            'vlm':"HTTPStatusError: 429 Too Many Requests - daily neuron quota exhausted"},now=datetime(2026,11,27,12,tzinfo=timezone.utc))
        self.assertGreaterEqual(delay,3600)
        self.assertLessEqual(delay,86400)

    def test_daily_neuron_budget_retries_just_after_next_utc_reset(self):
        # Reset is daily UTC, not an arbitrary 24h after hitting the limit.
        clock=datetime(2026,11,24,23,55,tzinfo=timezone.utc)
        delay=model_quota_retry_seconds(
            {'vlm':'429 daily Neuron quota exhausted'},now=clock)
        self.assertEqual(delay,900)

    def test_provider_temporary_outage_defers_without_false_completion(self):
        self.assertIsNotNone(model_quota_retry_seconds({
            'asr':'HTTPStatusError: 503 Service Unavailable'}))

    def test_regular_video_content_and_ocr_errors_are_not_misclassified(self):
        self.assertIsNone(model_quota_retry_seconds({
            'ocr':'ValueError: undecodable carousel page'}))
        self.assertIsNone(model_quota_retry_seconds({
            'vlm':'ValueError: malformed JSON shape'}))
        self.assertIsNone(model_quota_retry_seconds({}))

    def test_model_quota_retry_is_durably_acknowledged_not_completed(self):
        from contextlib import redirect_stdout
        import io
        outcome={'id':8,'status':'deferred_model_quota','acknowledged_failure':True,
                 'source_url':'https://www.instagram.com/reel/DoNotLeak/'}
        with redirect_stdout(io.StringIO()) as output:
            result=require_successful_batch([outcome])
        self.assertEqual(result,{'state':'deferred','completed':0,'deferred':1})
        self.assertIn('::warning::',output.getvalue())
        self.assertNotIn('DoNotLeak',output.getvalue())

    def test_unacknowledged_model_retry_never_counts_as_a_success(self):
        with self.assertRaises(RuntimeError) as raised:
            require_successful_batch([
                {'status':'deferred_model_quota','acknowledged_failure':False}])
        self.assertIn('acknowledged',str(raised.exception).lower())

if __name__=='__main__':unittest.main()
