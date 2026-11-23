import unittest
from pydantic import ValidationError
from reelbrain.contract import ExtractionResult, Evidence, reject_unsupported, candidates_from_result


def res(url, verbatim, **kw):
    return {"language": "hi-en", "summary": "s", "resources": [{"name": "Onyx", "kind": "github_repo", "observed_url": url,
            "evidence": [{"modality": "on_screen", "slide_index": 6, "verbatim": verbatim}]}], **kw}


class ContractTest(unittest.TestCase):
    def test_valid_roundtrip_and_schema(self):
        r = ExtractionResult.model_validate(res("github.com/onyx-dot-app/onyx", "github.com/onyx-dot-app/onyx"))
        self.assertEqual(r.resources[0].evidence[0].slide_index, 6)
        schema = ExtractionResult.model_json_schema()
        self.assertIn("resources", schema["properties"])

    def test_evidence_is_mandatory(self):
        bad = res(None, "x"); bad["resources"][0]["evidence"] = []
        with self.assertRaises(ValidationError):
            ExtractionResult.model_validate(bad)

    def test_timestamp_and_locator_rules(self):
        with self.assertRaises(ValidationError):
            Evidence(modality="speech", verbatim="hi")                     # no locator
        with self.assertRaises(ValidationError):
            Evidence(modality="on_screen", t_start="5s", verbatim="hi")    # not MM:SS
        Evidence(modality="caption", verbatim="caption text")              # caption needs no locator

    def test_unsupported_url_gate_strips_hallucination(self):
        r = ExtractionResult.model_validate(res("github.com/onyx-dot-app/onyx", "Onyx - enterprise search"))
        fixed, rejected = reject_unsupported(r, corpus=["Follow for more"])
        self.assertEqual(rejected[0]["reason"], "unsupported_url")
        self.assertIsNone(fixed.resources[0].observed_url)
        self.assertTrue(fixed.resources[0].uncertain_chars)

    def test_gate_accepts_url_seen_by_independent_ocr(self):
        r = ExtractionResult.model_validate(res("https://github.com/onyx-dot-app/onyx", "Onyx"))
        fixed, rejected = reject_unsupported(r, corpus=["Repo link:\ngithub.com / onyx-dot-app / onyx"])
        self.assertEqual(rejected, [])
        self.assertEqual(fixed.resources[0].observed_url, "https://github.com/onyx-dot-app/onyx")

    def test_candidates_from_result(self):
        r = ExtractionResult.model_validate(res("github.com/onyx-dot-app/onyx", "github.com/onyx-dot-app/onyx"))
        self.assertEqual([c.value for c in candidates_from_result(r)], ["onyx-dot-app/onyx"])


if __name__ == "__main__":
    unittest.main()
