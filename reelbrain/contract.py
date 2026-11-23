"""The structured-output contract for the multimodal pass, plus the 'unsupported URL' gate.
Use ExtractionResult.model_json_schema() as the response schema for Gemini structured output."""
from __future__ import annotations
import re
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from .links import extract_candidates, normalize_text_for_match

MMSS = re.compile(r"^\d{1,2}:\d{2}$")


class Evidence(BaseModel):
    modality: Literal["on_screen", "speech", "caption", "slide"]
    t_start: Optional[str] = Field(None, description="MM:SS where it first appears")
    t_end: Optional[str] = None
    slide_index: Optional[int] = Field(None, ge=1, description="1-based, carousels only")
    verbatim: str = Field(..., min_length=1, description="Exactly as seen/heard. Never paraphrase.")

    @field_validator("t_start", "t_end")
    @classmethod
    def _mmss(cls, v):
        if v is not None and not MMSS.match(v):
            raise ValueError("timestamps must be MM:SS")
        return v

    @model_validator(mode="after")
    def _locator(self):
        if self.modality in ("on_screen", "speech") and self.t_start is None and self.slide_index is None:
            raise ValueError("on_screen/speech evidence needs t_start or slide_index")
        return self


class Resource(BaseModel):
    name: str
    kind: Literal["github_repo", "npm_package", "pypi_package", "website", "command", "tool_name", "course", "other"]
    observed_url: Optional[str] = Field(None, description="Only if literally visible/audible. Never guess a URL.")
    claimed_purpose: Optional[str] = Field(None, description="What the creator CLAIMS; not verified")
    uncertain_chars: bool = Field(False, description="True if any character (O/0, l/1, rn/m) is doubtful")
    evidence: list[Evidence] = Field(..., min_length=1)


class Promise(BaseModel):
    what: str
    mechanism: Literal["comment_keyword", "dm", "link_in_bio", "other"]
    keyword: Optional[str] = None
    evidence: list[Evidence] = Field(..., min_length=1)


class ExtractionResult(BaseModel):
    language: str = Field(..., description="Dominant spoken language, e.g. hi, en, hi-en")
    summary: str = Field(..., max_length=400)
    resources: list[Resource] = []
    promises: list[Promise] = Field([], description="Guides/links promised via DM/comment; these stay unresolved")


def reject_unsupported(result: ExtractionResult, corpus: list[str]) -> "tuple[ExtractionResult, list[dict]]":
    """Gate: any observed_url must appear (normalised) in the evidence the model cited OR in independent text
    (OCR of frames, ASR, caption). Unsupported URLs are stripped and reported, never silently kept."""
    haystack = [normalize_text_for_match(t) for t in corpus]
    rejected, kept = [], []
    for r in result.resources:
        if r.observed_url:
            own = [normalize_text_for_match(e.verbatim) for e in r.evidence]
            target = normalize_text_for_match(r.observed_url)
            if not any(target and target in h for h in own + haystack):
                rejected.append({"name": r.name, "observed_url": r.observed_url, "reason": "unsupported_url"})
                r = r.model_copy(update={"observed_url": None, "uncertain_chars": True})
        kept.append(r)
    return result.model_copy(update={"resources": kept}), rejected


def candidates_from_result(result: ExtractionResult):
    """Everything the verifier should look at: resource URLs/commands plus anything extract_candidates finds in evidence."""
    texts = []
    for r in result.resources:
        texts.append(r.observed_url or "")
        texts += [e.verbatim for e in r.evidence]
    return extract_candidates("\n".join(t for t in texts if t))
