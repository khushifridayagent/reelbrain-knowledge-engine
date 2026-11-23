"""Verification ladder for resources found in a Reel. Network goes through an injectable `http` function,
so every path is testable offline. Only allowlisted hosts are ever fetched."""
from __future__ import annotations
import base64, json, math, urllib.error, urllib.parse, urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

from .links import is_safe_fetch_url, repair_variants

LADDER = ["seen", "exists", "readme_checked", "sandbox_run", "user_confirmed"]
NEW_REPO_DAYS, STALE_DAYS, LOW_STARS = 30, 365, 10     # heuristics, tune on your golden set

HttpFn = Callable[[str, dict], "tuple[int, Any]"]


def default_http(url: str, headers: dict) -> "tuple[int, Any]":
    """GET returning (status, parsed_json_or_None). Refuses non-allowlisted hosts."""
    if not is_safe_fetch_url(url):
        raise ValueError(f"blocked url: {url}")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except Exception:
            return e.code, None


@dataclass
class RepoFacts:
    full_name: str
    html_url: str
    stars: int
    license: Optional[str]
    pushed_at: Optional[str]
    created_at: Optional[str]
    archived: bool
    fork: bool
    description: Optional[str]
    topics: list = field(default_factory=list)


@dataclass
class Verification:
    status: str                      # verified | repaired_verified | resolved_by_search | ambiguous | not_found | rate_limited | error
    level: str                       # position on LADDER ("seen" when nothing was confirmed)
    observed: str                    # exactly what the Reel showed
    resolved: Optional[str] = None   # canonical owner/repo when found
    facts: Optional[RepoFacts] = None
    flags: list = field(default_factory=list)
    candidates: list = field(default_factory=list)   # for ambiguous results
    tried: int = 0                   # API calls spent on repair attempts


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def health_flags(f: RepoFacts, now: Optional[datetime] = None) -> list:
    now = now or datetime.now(timezone.utc)
    flags = []
    created, pushed = _parse_dt(f.created_at), _parse_dt(f.pushed_at)
    if created and (now - created).days < NEW_REPO_DAYS:
        flags.append("new_repo")
    if pushed and (now - pushed).days > STALE_DAYS:
        flags.append("stale")
    if f.stars < LOW_STARS:
        flags.append("low_stars")
    if f.archived:
        flags.append("archived")
    if f.fork:
        flags.append("fork")
    if not f.license:
        flags.append("no_license")
    return flags


def near_known(name: str, known: list, cutoff: float = 0.85) -> list:
    """Typosquat heuristic: names very similar to, but not equal to, a well-known package."""
    n = name.lower()
    return [k for k in known if k.lower() != n and SequenceMatcher(None, n, k.lower()).ratio() >= cutoff]


class GitHubVerifier:
    def __init__(self, http: HttpFn = default_http, token: Optional[str] = None,
                 now: Optional[Callable[[], datetime]] = None, max_repair_calls: int = 20):
        self.http = http
        self.max_repair_calls = max_repair_calls
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": "reelbrain/0.1"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    # -- single lookups ----------------------------------------------------------------------
    def repo(self, owner: str, name: str) -> "tuple[str, Optional[RepoFacts]]":
        status, data = self.http(f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}", self.headers)
        if status == 200 and isinstance(data, dict):
            lic = (data.get("license") or {}).get("spdx_id")
            return "ok", RepoFacts(data["full_name"], data["html_url"], int(data.get("stargazers_count", 0)), lic,
                                   data.get("pushed_at"), data.get("created_at"), bool(data.get("archived")),
                                   bool(data.get("fork")), data.get("description"), data.get("topics") or [])
        if status == 404:
            return "not_found", None
        if status in (403, 429):
            return "rate_limited", None
        return "error", None

    def readme(self, owner: str, name: str) -> Optional[str]:
        status, data = self.http(f"https://api.github.com/repos/{owner}/{name}/readme", self.headers)
        if status == 200 and isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", "replace")
        return None

    # -- the main entry ----------------------------------------------------------------------
    def verify(self, owner: str, name: str, allow_repair: bool = True) -> Verification:
        observed = f"{owner}/{name}"
        st, facts = self.repo(owner, name)
        if st == "ok":
            flags = health_flags(facts, self.now())
            if facts.full_name.lower() != observed.lower():
                flags.append("renamed_or_moved")
            return Verification("verified", "exists", observed, facts.full_name, facts, flags)
        if st in ("rate_limited", "error"):
            return Verification(st, "seen", observed)
        if not allow_repair:
            return Verification("not_found", "seen", observed)

        # OCR repair: vary the repo name first (owner usually a known brand), then the owner. Never both.
        hits: list = []
        calls = 0
        attempts = [(owner, v) for v in repair_variants(name)] + [(v, name) for v in repair_variants(owner)]
        for o, n in attempts:
            if calls >= self.max_repair_calls:
                break
            calls += 1
            st2, f2 = self.repo(o, n)
            if st2 == "rate_limited":
                return Verification("rate_limited", "seen", observed, tried=calls)
            if st2 == "ok" and f2.full_name.lower() not in [h.full_name.lower() for h in hits]:
                hits.append(f2)
        if len(hits) == 1:
            f = hits[0]
            return Verification("repaired_verified", "exists", observed, f.full_name, f,
                                health_flags(f, self.now()) + ["ocr_repaired"], tried=calls)
        if len(hits) > 1:
            return Verification("ambiguous", "seen", observed, candidates=[h.full_name for h in hits], tried=calls,
                                flags=["requires_review"])
        return Verification("not_found", "seen", observed, tried=calls)

    # -- name-only mentions ("Onyx", "Scrapling") ----------------------------------------------
    def search_by_name(self, name: str, hints: str = "") -> Verification:
        q = urllib.parse.quote(f"{name} in:name")
        status, data = self.http(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=5", self.headers)
        if status in (403, 429):
            return Verification("rate_limited", "seen", name)
        if status != 200 or not isinstance(data, dict) or not data.get("items"):
            return Verification("not_found", "seen", name)
        hint_tokens = {t for t in hints.lower().split() if len(t) > 3}
        scored = []
        for it in data["items"]:
            text = f"{it.get('description') or ''} {' '.join(it.get('topics') or [])}".lower()
            exact = it["name"].lower() == name.lower()
            score = (3.0 if exact else 0.0) + math.log10(1 + it.get("stargazers_count", 0)) + sum(1 for t in hint_tokens if t in text)
            scored.append((score, it))
        scored.sort(key=lambda x: -x[0])
        top, second = scored[0][1], (scored[1][1] if len(scored) > 1 else None)
        dominant = top["name"].lower() == name.lower() and (
            second is None or top.get("stargazers_count", 0) >= 5 * max(1, second.get("stargazers_count", 0)))
        if dominant:
            st, f = self.repo(*top["full_name"].split("/", 1))
            if st == "ok":
                return Verification("resolved_by_search", "exists", name, f.full_name, f,
                                    health_flags(f, self.now()) + ["resolved_by_name_search"])
        return Verification("ambiguous", "seen", name, candidates=[s[1]["full_name"] for s in scored], flags=["requires_review"])
