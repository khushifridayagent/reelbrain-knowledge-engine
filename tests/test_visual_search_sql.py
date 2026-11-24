"""Source screenshots and diagrams must be searchable, not merely stored."""
import unittest
from pathlib import Path

class VisualSearchSQLTests(unittest.TestCase):
    def test_source_ocr_qr_and_visual_model_inference_searchable_with_correct_provenance(self):
        path=Path(__file__).resolve().parents[1]/'sql'/'0032_search_visual_ocr_qr_evidence.sql'
        text=path.read_text(encoding='utf-8')
        self.assertIn('reelbrain_research.reel_observations',text)
        self.assertIn("'qr'",text)
        self.assertIn("'ocr'",text)
        self.assertIn("'model_inference'",text)
        self.assertIn("'visual_model_inference'",text)
        self.assertIn("'onscreen_qr_source'",text)
        self.assertIn("'onscreen_ocr_source'",text)
        self.assertIn('source_url||',text)
        self.assertIn('o.locator',text)
        self.assertNotIn('GRANT EXECUTE ON FUNCTION',text.upper())


if __name__=='__main__':unittest.main()
