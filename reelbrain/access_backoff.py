"""Bounded retry policy for temporarily unavailable Instagram public media.

A failed downloader is not a model-processing failure; preserve queued jobs
with a long backoff instead of burning through the finite bug retry budget.
"""
from __future__ import annotations

from .public_media import PublicMediaError


def access_backoff_seconds(error: BaseException) -> int | None:
    """Return a long per-source defer interval, or None for an actual code error.

    Does not inspect cookies or expose raw provider stderr; upstream
    PublicMediaError has already sanitized external provider responses.
    """
    if not isinstance(error, PublicMediaError):
        return None
    reason=str(error).lower()[:400]
    if 'credits_exhausted' in reason or 'credential_invalid' in reason:
        return 24 * 3600
    if 'rate_limited' in reason or 'too many requests' in reason:
        return 12 * 3600
    if 'http_forbidden' in reason or 'login_required' in reason:
        return 6 * 3600
    if any(tag in reason for tag in (
            'public media unavailable',
            'public reel download unavailable',
            'no valid bounded mp4',
            'no public media files',
            'no valid reel video',
            'gallery contains unverified',
            'gallery exceeds',
            'reel acquisition timed out',
            'gallery-dl public extraction timed out')):
        return 2 * 3600
    return None
