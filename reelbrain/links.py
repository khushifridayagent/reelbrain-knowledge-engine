"""Candidate extraction, OCR-confusion repair and URL safety. Pure functions, no network."""
from __future__ import annotations
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

# Hosts we are willing to fetch for verification (SSRF guard). Everything else is data only.
FETCH_ALLOWLIST = {"github.com", "api.github.com", "registry.npmjs.org", "pypi.org"}

_NAME = r"[A-Za-z0-9_.\-]+"
# tolerant of OCR spacing around slashes: "github.com / owner / repo"
GITHUB_RE = re.compile(rf"(?:https?://)?(?:www\.)?github\.com\s*/\s*({_NAME})\s*/\s*({_NAME})", re.I)
NPM_RE = re.compile(r"\b(?:npm\s+(?:i|install|add)(?:\s+-[-\w]+)*|npx|pnpm\s+add|yarn\s+add)\s+(@?[\w.\-]+(?:/[\w.\-]+)?)", re.I)
PIP_RE = re.compile(r"\b(?:pip3?|uv\s+pip|uv\s+add|pipx)\s+(?:install\s+)?(?:-[-\w]+\s+)*([A-Za-z0-9][\w.\-]*)", re.I)
CLONE_RE = re.compile(r"\bgit\s+clone\s+(\S+)", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)
BARE_REPO_RE = re.compile(rf"(?<![\w/.\-])({_NAME})/({_NAME})(?![\w/])")
_TRAIL = ".,;:!?)]}'\""
URLISH_TRIGGER = re.compile(r"github|https?://|npm\s|npx\s|pip\s|pip3\s|git\s+clone|\.com\b|\.io\b|\.ai\b|\.dev\b", re.I)


@dataclass(frozen=True)
class Candidate:
    kind: str            # github_repo | npm_package | pypi_package | url
    value: str           # canonical form, e.g. "owner/repo" or "package"
    raw: str             # exactly what was observed
    owner: str | None = None
    name: str | None = None


def _clean(s: str) -> str:
    s = s.strip().rstrip(_TRAIL)
    return s[:-4] if s.lower().endswith(".git") else s


def extract_candidates(text: str) -> list[Candidate]:
    """Find GitHub repos, npm/pip packages, git-clone targets and generic URLs in free text."""
    out: list[Candidate] = []
    seen: set[tuple[str, str]] = set()

    def add(c: Candidate):
        key = (c.kind, c.value.lower())
        if key not in seen:
            seen.add(key)
            out.append(c)

    for m in GITHUB_RE.finditer(text):
        owner, name = _clean(m.group(1)), _clean(m.group(2))
        if owner and name:
            add(Candidate("github_repo", f"{owner}/{name}", m.group(0), owner, name))
    for m in CLONE_RE.finditer(text):
        for g in GITHUB_RE.finditer(m.group(1)):
            owner, name = _clean(g.group(1)), _clean(g.group(2))
            add(Candidate("github_repo", f"{owner}/{name}", m.group(0), owner, name))
    for m in NPM_RE.finditer(text):
        pkg = _clean(m.group(1))
        add(Candidate("npm_package", pkg, m.group(0), None, pkg))
    for m in PIP_RE.finditer(text):
        pkg = _clean(m.group(1))
        if pkg.lower() not in {"install", "pip", "pip3", "uv", "-r", "-e"}:
            add(Candidate("pypi_package", pkg, m.group(0), None, pkg))
    for m in URL_RE.finditer(text):
        u = _clean(m.group(0))
        if "github.com/" not in u.lower():
            add(Candidate("url", u, m.group(0)))
    # bare "owner/repo" only when the same text mentions github (avoids matching 'and/or', dates, paths)
    if re.search(r"github", text, re.I):
        for m in BARE_REPO_RE.finditer(text):
            owner, name = _clean(m.group(1)), _clean(m.group(2))
            if owner and name and not owner.isdigit() and "." not in owner and len(owner) > 1 and len(name) > 1:
                add(Candidate("github_repo", f"{owner}/{name}", m.group(0), owner, name))
    return out


def looks_url_ish(text: str) -> bool:
    """Cheap trigger used to decide whether a frame deserves a dense re-sample."""
    return bool(URLISH_TRIGGER.search(text))


# ---- OCR confusion repair -------------------------------------------------------------------
CONFUSIONS = [("0", "o"), ("o", "0"), ("1", "l"), ("l", "1"), ("1", "i"), ("i", "1"), ("l", "i"), ("i", "l"),
              ("rn", "m"), ("m", "rn"), ("vv", "w"), ("w", "vv"), ("5", "s"), ("s", "5"), ("8", "b"), ("b", "8")]


def repair_variants(s: str, max_subs: int = 2, limit: int = 24) -> list[str]:
    """Lower-cased spelling variants of s by plausible OCR confusions, fewest substitutions first.
    GitHub names are case-insensitive, so case is not varied."""
    s = s.lower()
    seen, out, frontier = {s}, [], [s]
    for _ in range(max_subs):
        nxt = []
        for cur in frontier:
            for a, b in CONFUSIONS:
                start = 0
                while (i := cur.find(a, start)) >= 0:
                    cand = cur[:i] + b + cur[i + len(a):]
                    if cand not in seen:
                        seen.add(cand)
                        out.append(cand)
                        nxt.append(cand)
                        if len(out) >= limit:
                            return out
                    start = i + 1
        frontier = nxt
    return out


# ---- URL safety -----------------------------------------------------------------------------
def is_safe_fetch_url(url: str) -> bool:
    """True only for https URLs on the allowlist: no userinfo, no custom port, no IP literals."""
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        return False
    if p.port not in (None, 443):
        return False
    host = p.hostname.lower()
    if re.fullmatch(r"[\d.]+|[\da-f:]+", host):
        return False
    return host in FETCH_ALLOWLIST


def normalize_text_for_match(s: str) -> str:
    """Used by the 'unsupported URL' gate: case-fold, drop scheme/www/trailing slash and all whitespace."""
    s = s.lower()
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    s = re.sub(r"\s+", "", s)
    return s.rstrip("/.")
