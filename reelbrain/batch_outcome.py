"""Translate durable worker outcomes into an honest scheduler result.

The queue's retry/dead-letter transaction can succeed even when actual media
acquisition fails. A successful acknowledgement must not make the external
scheduler claim successful media extraction.
"""
from __future__ import annotations


def require_successful_batch(outcomes: list[dict]) -> None:
    """Raise a sanitized error for unsuccessful work; never echo a Reel URL.

    An idle queue is not an error, but a failed attempt is. The database queue
    has already been updated by run_one_batch before this function is called.
    """
    for outcome in outcomes:
        status = outcome.get("status") if isinstance(outcome, dict) else None
        if status == "deferred_access":
            if not outcome.get("acknowledged_failure"):
                raise RuntimeError("Media access deferral could not be acknowledged in the durable queue")
            raise RuntimeError("Instagram public media is inaccessible; job safely deferred without exhausting retries")
        if status == "retry_or_dead_letter":
            if not outcome.get("acknowledged_failure"):
                raise RuntimeError("Media failure was not acknowledged by the durable queue")
            raise RuntimeError("Media acquisition/processing failed; queue safely scheduled a retry or dead-letter")
        if status not in {"evidence_saved", "partial", "processed"}:
            raise RuntimeError("Unexpected media worker result; refusing false success")
