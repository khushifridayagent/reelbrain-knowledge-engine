"""Opt-in, budgeted public Instagram Reel video acquisition with yt-dlp.

No login cookies, no authentication bypass, no scraping of private accounts.
This downloader is a best-effort alternative to paid Apify; Instagram may refuse.
Never claim media processing until an actual bounded MP4 has been downloaded.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit
import re
import subprocess


class PublicMediaError(RuntimeError):
    """Media unavailable or refused; caller must retry/defer, not mark processed."""


_SHORTCODE = re.compile(r"^[A-Za-z0-9_-]{4,160}$")


def canonical_reel(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise PublicMediaError("Invalid Reel URL")
    try:
        p = urlsplit(url)
        segments = [x for x in p.path.split("/") if x]
        if (p.scheme != "https" or p.hostname not in {"instagram.com", "www.instagram.com"}
                or p.username or p.password or p.port or p.fragment
                or len(segments) != 2 or segments[0] != "reel" or not _SHORTCODE.fullmatch(segments[1])):
            raise PublicMediaError("Only public HTTPS Instagram Reel URLs are supported")
        return f"https://www.instagram.com/reel/{segments[1]}/"
    except ValueError as exc:
        raise PublicMediaError("Invalid Reel URL") from exc


def _valid_media(path: Path, max_bytes: int) -> bool:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        return False
    if path.stat().st_size < 16:
        return False
    with path.open('rb') as stream:
        return stream.read(12)[4:8] == b'ftyp'


def acquire_public_reel(url: str, output_directory: str | Path, *, max_bytes: int = 100 * 1024 * 1024,
                        timeout_seconds: int = 210, runner=None) -> Path:
    """Download exactly one public Reel into a private temporary directory.

    Requires explicit caller authorization and media-use rights; this adapter
    never loads browser cookies and cannot access login-only/private Reels.
    May fail because Instagram blocks unsigned/anonymous downloads.
    """
    canonical = canonical_reel(url)
    if not 1024 <= max_bytes <= 100 * 1024 * 1024:
        raise PublicMediaError('Invalid maximum media size')
    if not 10 <= timeout_seconds <= 600:
        raise PublicMediaError('Invalid download time budget')
    root = Path(output_directory)
    if root.is_symlink() or not root.exists() or not root.is_dir():
        raise PublicMediaError('Output directory is not a safe existing directory')
    shortcode = canonical.rstrip('/').rsplit('/', 1)[-1]
    target = root / f'{shortcode}.mp4'
    if target.exists() or target.is_symlink():
        raise PublicMediaError('Refusing existing media output path')
    max_megabytes = max(1, max_bytes // (1024 * 1024))
    cmd = [
        'yt-dlp', '--ignore-config', '--no-playlist', '--no-cookies-from-browser',
        '--no-cache-dir', '--no-progress', '--no-warnings', '--no-colors',
        '--no-write-info-json', '--no-write-thumbnail', '--no-write-comments',
        '--max-downloads', '1', '--max-filesize', f'{max_megabytes}M',
        '--format', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
        '--merge-output-format', 'mp4', '--output', str(root / (shortcode + '.%(ext)s')),
        canonical,
    ]
    try:
        run = runner or subprocess.run
        result = run(cmd, capture_output=True, text=True, timeout=timeout_seconds,
                     check=False, stdin=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        raise PublicMediaError('yt-dlp is not installed') from exc
    except subprocess.TimeoutExpired as exc:
        raise PublicMediaError('Public Reel acquisition timed out') from exc
    if result.returncode:
        # yt-dlp stderr can contain private URLs/credentials in other contexts.
        # Do not persist or reveal its raw untrusted provider error.
        raise PublicMediaError('Public Reel download unavailable (yt-dlp failed)')
    if not _valid_media(target, max_bytes):
        raise PublicMediaError('No valid bounded MP4 returned by public Reel extractor')
    return target