"""Bounded public acquisition for a Reel OR a complete multi-slide Instagram post.

yt-dlp is tried for a Reel. gallery-dl is a separate no-cookie best-effort
fallback and is primary for carousel posts. Neither bypasses Instagram access
controls. Media only lives in a caller-managed temporary directory.
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .public_media import PublicMediaError, acquire_public_reel
from .sources import canonicalize_instagram


class PublicBundleError(PublicMediaError):
    """No trustworthy, complete media bundle was obtained."""


@dataclass(frozen=True)
class PublicBundle:
    paths: tuple[Path, ...]
    provider: str


def _sort_key(path: Path) -> list:
    # Homogeneous tuple keys prevent mixed numeric/text filenames from
    # comparing int against str during carousel ordering.
    return [(1,int(part)) if part.isdigit() else (0,part.lower())
            for part in re.split(r'(\d+)', path.name)]


def _valid_asset(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or not 32 <= path.stat().st_size <= 100 * 1024 * 1024:
        return False
    with path.open('rb') as inp:
        magic = inp.read(16)
    suffix = path.suffix.lower()
    if suffix in ('.mp4', '.m4v', '.mov'):
        return magic[4:8] == b'ftyp'
    if suffix in ('.jpg', '.jpeg'):
        return magic.startswith(bytes.fromhex('ffd8ff'))
    if suffix == '.png':
        return magic.startswith(bytes.fromhex('89504e470d0a1a0a'))
    if suffix == '.webp':
        return magic.startswith(b'RIFF') and magic[8:12] == b'WEBP'
    return False


def _category(stderr: str) -> str:
    # Provider errors may contain media addresses, cookies or other secrets.
    # Only fixed, bounded categories reach logs/database.
    low = (stderr or '').lower()[:16000]
    if any(s in low for s in ('429', 'rate limit', 'too many requests')):
        return 'rate_limited'
    if any(s in low for s in ('login', 'log in', 'sign in', 'cookie', 'redirect to login')):
        return 'login_required'
    if any(s in low for s in ('403', 'access denied', 'forbidden')):
        return 'http_forbidden'
    if any(s in low for s in ('not found', 'unsupported', 'no media', 'empty media response', '404')):
        return 'extractor_unavailable'
    return 'unavailable'


def acquire_public_bundle(
    url: str, output_directory: str | Path, *, max_items: int = 20,
    max_total_bytes: int = 300 * 1024 * 1024, timeout_seconds: int = 180,
    yt_runner=None, gallery_runner=None, cookies_file: Path | None = None,
) -> PublicBundle:
    """Download up to 20 ordered post assets; fail if coverage is uncertain.

    An extractor reporting success with zero media or an HTML login page is NOT
    treated as successful processing. All storage is transient and budgeted.
    """
    canonical = canonicalize_instagram(url)
    if not 1 <= max_items <= 20 or not 1_024 <= max_total_bytes <= 300 * 1024 * 1024:
        raise PublicBundleError('Invalid media resource budget')
    if not 10 <= timeout_seconds <= 600:
        raise PublicBundleError('Invalid download time budget')
    root = Path(output_directory)
    if root.is_symlink() or not root.is_dir():
        raise PublicBundleError('Output directory must be an existing safe directory')
    if cookies_file is not None:
        cookie = Path(cookies_file)
        if cookie.is_symlink() or not cookie.is_file() or (cookie.stat().st_mode & 0o077):
            raise PublicBundleError('Session file missing or insufficiently private')
    reel_problem = ''
    if '/reel/' in canonical or '/tv/' in canonical:
        folder = root / 'yt'
        folder.mkdir(mode=0o700)
        try:
            path = acquire_public_reel(canonical, folder, timeout_seconds=timeout_seconds,
                                       runner=yt_runner, cookies_file=cookies_file)
            if not _valid_asset(path):
                raise PublicBundleError('No valid Reel video received from yt-dlp')
            return PublicBundle((path,), 'yt-dlp-public')
        except PublicMediaError as exc:
            reel_problem = str(exc)[:120]
    folder = root / 'gallery'
    folder.mkdir(mode=0o700)
    argv = [
        'gallery-dl', '--config-ignore', '--no-input', '--no-colors',
        '--no-postprocessors', '--no-part', '--retries', '1',
        '--http-timeout', '20', '--filesize-max', '100M',
        '--range', f'1-{max_items + 1}', '-D', str(folder), canonical,
    ]
    is_post = '/p/' in canonical
    if is_post:
        argv[argv.index('--no-postprocessors')] = '--write-metadata'
        # Metadata and original downloaded bytes remain in the private temp directory.
        argv[1:1] = ['-o','extractor.instagram.previews=false','-o','extractor.instagram.audio=false']
    if cookies_file is not None:
        argv[1:1] = ['--cookies', str(cookies_file)]
    try:
        proc = (gallery_runner or subprocess.run)(
            argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            check=False, timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise PublicBundleError('gallery-dl is not installed') from exc
    except subprocess.TimeoutExpired as exc:
        raise PublicBundleError('gallery-dl public extraction timed out') from exc
    if proc.returncode:
        reason = _category(getattr(proc, 'stderr', '') or '')
        raise PublicBundleError('Public media unavailable: gallery_' + reason +
                                ('; first_provider_failed' if reel_problem else ''))
    children = list(folder.iterdir())
    if any(child.is_symlink() or not child.is_file() for child in children):
        raise PublicBundleError('Unsafe/unexpected gallery output structure')
    if is_post:
        paths = [child for child in children if child.suffix.lower() != '.json']
        expected_code=canonical.rstrip('/').rsplit('/',1)[-1]
        manifest=[]
        for path in paths:
            sidecar=path.with_name(path.name+'.json')
            try:
                if sidecar.is_symlink() or not sidecar.is_file() or sidecar.stat().st_size>2*1024*1024:
                    raise ValueError()
                data=json.loads(sidecar.read_text(encoding='utf-8'))
                count=data.get('count')
                index=data.get('num',1 if count==1 else None)
                if (data.get('post_shortcode')!=expected_code or type(count) is not int
                        or type(index) is not int or not 1<=count<=max_items
                        or not 1<=index<=count or
                        (count==1 and (data.get('typename')=='GraphSidecar' or data.get('sidecar_shortcode')))):
                    raise ValueError()
                manifest.append((index,count,path))
            except (ValueError,OSError,TypeError,AttributeError):
                raise PublicBundleError('Public media unavailable: carousel_manifest_unverified') from None
        if (not manifest or any(count!=len(paths) for _,count,_ in manifest)
                or sorted(index for index,_,_ in manifest)!=list(range(1,len(paths)+1))):
            raise PublicBundleError('Public media unavailable: carousel_manifest_incomplete')
        paths=[path for _,_,path in sorted(manifest,key=lambda row:row[0])]
        for child in children:
            if child.suffix.lower()=='.json':
                child.unlink()
    else:
        paths = sorted(children, key=_sort_key)
    if not paths:
        raise PublicBundleError('No public media files found')
    if len(paths) > max_items:
        raise PublicBundleError('Carousel exceeds supported slide count; incomplete extraction refused')
    if any(not _valid_asset(p) for p in paths):
        raise PublicBundleError('Gallery contains unverified or unsupported media bytes')
    if ('/reel/' in canonical or '/tv/' in canonical) and not any(
            p.suffix.lower() in ('.mp4','.m4v','.mov') for p in paths):
        raise PublicBundleError('Public media unavailable: reel_original_video_missing')
    if sum(p.stat().st_size for p in paths) > max_total_bytes:
        raise PublicBundleError('Media bundle exceeds bounded total size')
    return PublicBundle(tuple(paths), 'gallery-dl-public')
