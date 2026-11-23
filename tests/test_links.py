import unittest
from reelbrain.links import (extract_candidates, repair_variants, is_safe_fetch_url, looks_url_ish, normalize_text_for_match)


class LinksTest(unittest.TestCase):
    def kinds(self, text):
        return {(c.kind, c.value.lower()) for c in extract_candidates(text)}

    def test_github_url_variants(self):
        got = self.kinds("see https://github.com/onyx-dot-app/onyx, also github.com / D4Vinci / Scrapling.")
        self.assertIn(("github_repo", "onyx-dot-app/onyx"), got)
        self.assertIn(("github_repo", "d4vinci/scrapling"), got)   # OCR spacing around slashes tolerated

    def test_trailing_punctuation_and_dot_git(self):
        got = self.kinds("git clone https://github.com/blader/humanizer.git)")
        self.assertIn(("github_repo", "blader/humanizer"), got)

    def test_install_commands(self):
        got = self.kinds("npm i -g @scope/tool\nnpx create-thing\npip install rich-click\nuv add httpx")
        self.assertIn(("npm_package", "@scope/tool"), got)
        self.assertIn(("npm_package", "create-thing"), got)
        self.assertIn(("pypi_package", "rich-click"), got)
        self.assertIn(("pypi_package", "httpx"), got)

    def test_bare_owner_repo_needs_github_context(self):
        self.assertEqual(self.kinds("and/or either/or 12/05"), set())
        self.assertIn(("github_repo", "mvanhorn/last30days-skill"), self.kinds("GitHub: mvanhorn/last30days-skill"))

    def test_url_trigger(self):
        self.assertTrue(looks_url_ish("Repo link: github.com/x/y"))
        self.assertFalse(looks_url_ish("Follow for more"))

    def test_repair_variants_cover_common_ocr_errors(self):
        v = repair_variants("0nyx-d0t-app")
        self.assertIn("onyx-d0t-app", v)           # one substitution
        self.assertIn("onyx-dot-app", v)           # two substitutions
        self.assertNotIn("0nyx-d0t-app", v)
        self.assertIn("modern", repair_variants("rnodern"))
        self.assertLessEqual(len(repair_variants("lllllllllll", limit=24)), 24)

    def test_ssrf_guard(self):
        ok = ["https://api.github.com/repos/a/b", "https://registry.npmjs.org/x", "https://pypi.org/pypi/x/json"]
        bad = ["http://api.github.com/x", "https://169.254.169.254/latest", "https://localhost/x", "https://evil.com/x",
               "https://api.github.com:8443/x", "https://user:pw@github.com/x", "https://github.com.evil.com/x", "file:///etc/passwd"]
        for u in ok: self.assertTrue(is_safe_fetch_url(u), u)
        for u in bad: self.assertFalse(is_safe_fetch_url(u), u)

    def test_normalizer(self):
        self.assertEqual(normalize_text_for_match("https://www.GitHub.com/A/b/"), normalize_text_for_match("github.com / a / B"))


if __name__ == "__main__":
    unittest.main()
