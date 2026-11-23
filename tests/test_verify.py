import unittest
from datetime import datetime, timezone
from reelbrain.verify import GitHubVerifier, health_flags, near_known, RepoFacts
import base64

NOW = datetime(2026, 11, 20, tzinfo=timezone.utc)


def repo_json(full, stars=500, created="2024-01-01T00:00:00Z", pushed="2026-11-01T00:00:00Z", lic="MIT", **kw):
    d = {"full_name": full, "html_url": f"https://github.com/{full}", "stargazers_count": stars, "created_at": created,
         "pushed_at": pushed, "archived": False, "fork": False, "description": kw.get("description", ""),
         "topics": kw.get("topics", []), "license": {"spdx_id": lic} if lic else None}
    return d


class FakeHttp:
    def __init__(self, repos, search=None, readmes=None, rate_limit_after=None):
        self.repos = {k.lower(): v for k, v in repos.items()}
        self.search, self.readmes, self.calls = search, readmes or {}, []
        self.rate_limit_after = rate_limit_after

    def __call__(self, url, headers):
        self.calls.append(url)
        if self.rate_limit_after is not None and len(self.calls) > self.rate_limit_after:
            return 403, None
        if "/search/repositories" in url:
            return 200, self.search
        if url.endswith("/readme"):
            key = url.split("/repos/")[1][:-7].lower()
            return (200, self.readmes[key]) if key in self.readmes else (404, None)
        key = url.split("/repos/")[1].lower()
        return (200, self.repos[key]) if key in self.repos else (404, None)


class VerifyTest(unittest.TestCase):
    def v(self, http, **kw):
        return GitHubVerifier(http=http, now=lambda: NOW, **kw)

    def test_exact_hit(self):
        h = FakeHttp({"onyx-dot-app/onyx": repo_json("onyx-dot-app/onyx")})
        r = self.v(h).verify("onyx-dot-app", "onyx")
        self.assertEqual((r.status, r.level, r.resolved), ("verified", "exists", "onyx-dot-app/onyx"))
        self.assertEqual(len(h.calls), 1)
        self.assertEqual(r.flags, [])

    def test_ocr_repair_single_hit(self):
        h = FakeHttp({"onyx-dot-app/onyx": repo_json("onyx-dot-app/onyx")})
        r = self.v(h).verify("onyx-dot-app", "0nyx")           # '0' read instead of 'o'
        self.assertEqual((r.status, r.resolved), ("repaired_verified", "onyx-dot-app/onyx"))
        self.assertIn("ocr_repaired", r.flags)
        self.assertEqual(r.observed, "onyx-dot-app/0nyx")      # the observed string is never overwritten

    def test_repair_ambiguous_goes_to_review_not_guess(self):
        h = FakeHttp({"a/mod": repo_json("a/mod")})
        r = self.v(h).verify("a", "rnod")                       # 'rn' read for 'm': exactly one repo resolves
        self.assertEqual((r.status, r.resolved), ("repaired_verified", "a/mod"))
        both = FakeHttp({"a/mod": repo_json("a/mod"), "a/m0d": repo_json("a/m0d")})
        self.assertEqual(self.v(both).verify("a", "rnod").status, "ambiguous")   # two plausible repos: never guess
        h2 = FakeHttp({"a/lol": repo_json("a/lol"), "a/101": repo_json("a/101"), "a/l0l": repo_json("a/l0l")})
        r2 = self.v(h2).verify("a", "1o1")
        self.assertEqual(r2.status, "ambiguous")
        self.assertIn("requires_review", r2.flags)
        self.assertGreaterEqual(len(r2.candidates), 2)

    def test_not_found_and_call_budget(self):
        h = FakeHttp({})
        r = self.v(h, max_repair_calls=5).verify("ghost", "llllll")
        self.assertEqual(r.status, "not_found")
        self.assertLessEqual(len(h.calls), 6)                   # 1 exact + at most 5 repairs

    def test_rate_limit_is_not_not_found(self):
        h = FakeHttp({}, rate_limit_after=0)
        self.assertEqual(self.v(h).verify("a", "b").status, "rate_limited")

    def test_no_repair_flag(self):
        h = FakeHttp({"a/b": repo_json("a/b")})
        self.assertEqual(self.v(h).verify("a", "x", allow_repair=False).status, "not_found")
        self.assertEqual(len(h.calls), 1)

    def test_health_flags(self):
        f = RepoFacts("a/b", "u", 3, None, "2024-01-01T00:00:00Z", "2026-11-10T00:00:00Z", True, True, None)
        self.assertEqual(set(health_flags(f, NOW)), {"new_repo", "stale", "low_stars", "archived", "fork", "no_license"})
        f2 = RepoFacts("a/b", "u", 5000, "MIT", "2026-11-01T00:00:00Z", "2023-01-01T00:00:00Z", False, False, None)
        self.assertEqual(health_flags(f2, NOW), [])

    def test_name_search_dominant_resolves(self):
        items = [{"name": "onyx", "full_name": "onyx-dot-app/onyx", "stargazers_count": 20000, "description": "enterprise search", "topics": []},
                 {"name": "onyx-js", "full_name": "x/onyx-js", "stargazers_count": 12, "description": "", "topics": []}]
        h = FakeHttp({"onyx-dot-app/onyx": repo_json("onyx-dot-app/onyx", stars=20000)}, search={"items": items})
        r = self.v(h).search_by_name("Onyx", "enterprise search tool")
        self.assertEqual((r.status, r.resolved), ("resolved_by_search", "onyx-dot-app/onyx"))
        self.assertIn("resolved_by_name_search", r.flags)

    def test_name_search_close_race_is_ambiguous(self):
        items = [{"name": "ponytail", "full_name": "a/ponytail", "stargazers_count": 100, "description": "", "topics": []},
                 {"name": "ponytail", "full_name": "b/ponytail", "stargazers_count": 90, "description": "", "topics": []}]
        r = self.v(FakeHttp({}, search={"items": items})).search_by_name("ponytail")
        self.assertEqual(r.status, "ambiguous")
        self.assertEqual(set(r.candidates), {"a/ponytail", "b/ponytail"})

    def test_readme_decode(self):
        body = {"encoding": "base64", "content": base64.b64encode("# Title\nnpm i foo".encode()).decode()}
        h = FakeHttp({}, readmes={"a/b": body})
        self.assertIn("npm i foo", self.v(h).readme("a", "b"))
        self.assertIsNone(self.v(h).readme("a", "zzz"))

    def test_typosquat_heuristic(self):
        self.assertEqual(near_known("reqeusts", ["requests", "numpy"]), ["requests"])
        self.assertEqual(near_known("requests", ["requests"]), [])


if __name__ == "__main__":
    unittest.main()
