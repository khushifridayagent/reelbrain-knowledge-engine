"""Report durable batch outcomes without disguising failed media extraction."""
from __future__ import annotations


_DEFERRED = {
    "deferred_access": (
        "Media access deferral could not be acknowledged in the durable queue",
        "Instagram public media is inaccessible; job safely deferred without exhausting retries",
    ),
    "deferred_model_quota": (
        "Model quota deferral was not acknowledged by the durable queue",
        "Hosted video/audio model quota unavailable; Reel safely queued for later retry",
    ),
    "deferred_progress": (
        "Incomplete media deferral was not acknowledged by the durable queue",
        "Media coverage pending; saved checkpoints will resume",
    ),
    "deferred_incomplete": (
        "Incomplete media deferral was not acknowledged by the durable queue",
        "Required media stage incomplete; durable retry scheduled",
    ),
}


def require_successful_batch(outcomes: list[dict]) -> None:
    """Fail on hard errors or no completed media in a deferred batch.

    Mixed persisted successes and durably acknowledged deferrals are reported
    as partial batch progress, not total failure. Deferred jobs remain queued
    and never count as completed. Unknown or unacknowledged outcomes are fatal.
    """
    deferred = []
    completed = 0
    for outcome in outcomes:
        status = outcome.get("status") if isinstance(outcome, dict) else None
        if not isinstance(status, str):
            raise RuntimeError("Unexpected media worker result; refusing false success")
        if status in _DEFERRED:
            unacknowledged, message = _DEFERRED[status]
            if outcome.get("acknowledged_failure") is not True:
                raise RuntimeError(unacknowledged)
            deferred.append(message)
            continue
        if status == "retry_or_dead_letter":
            if outcome.get("acknowledged_failure") is not True:
                raise RuntimeError("Media failure was not acknowledged by the durable queue")
            raise RuntimeError("Media acquisition/processing failed; queue safely scheduled a retry or dead-letter")
        if status not in {"evidence_saved", "partial", "processed"}:
            raise RuntimeError("Unexpected media worker result; refusing false success")
        if status in {"evidence_saved", "processed"}:
            completed += 1
    if deferred:
        if not completed:
            raise RuntimeError(deferred[0])
        print(f"::warning::Mixed media batch: {completed} persisted successes, "
              f"{len(deferred)} safely deferred; deferred items are not complete.")
