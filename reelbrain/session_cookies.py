"""Safely materialize an optional Instagram Netscape cookies.txt GitHub secret.

Use only a user-authorized session and respect account access restrictions.
Never print, persist to public artifacts, or export credentials from the runner.
"""
from __future__ import annotations
import base64
import binascii
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager


@contextmanager
def temporary_instagram_cookies():
    encoded=os.environ.get('REELBRAIN_INSTAGRAM_COOKIES_B64','')
    if not encoded:
        yield None
        return
    if len(encoded)>512_000:
        raise ValueError('Instagram cookie secret exceeds bounded size')
    try:
        raw=base64.b64decode(encoded,validate=True)
    except (binascii.Error,ValueError) as exc:
        raise ValueError('Instagram cookie secret is not valid base64') from exc
    if not raw.startswith(b'# Netscape HTTP Cookie File') or len(raw)>384_000:
        raise ValueError('Expected a Netscape cookies.txt format secret')
    # Only Instagram-domain cookies. Avoid accidentally passing other sites'
    # authentication data to an extractor, even if a user exported all cookies.
    try:
        lines=raw.decode('utf-8').splitlines()
        for line in lines:
            if line.startswith('#HttpOnly_'):
                line=line.removeprefix('#HttpOnly_')
            elif line.startswith('#'):
                continue
            if not line.strip():
                continue
            fields=line.split('\t')
            if len(fields)!=7 or not (fields[0].lstrip('.').lower()=='instagram.com' or
                                      fields[0].lstrip('.').lower().endswith('.instagram.com')):
                raise ValueError('Cookie file includes non-Instagram cookies or invalid format')
    except UnicodeError as exc:
        raise ValueError('Cookie file is not UTF-8') from exc
    with tempfile.TemporaryDirectory(prefix='rb_ig_session_') as tmp:
        dest=Path(tmp)/'cookies.txt'
        with dest.open('xb') as stream:
            stream.write(raw)
        os.chmod(dest,0o600)
        try:
            yield dest
        finally:
            dest.unlink(missing_ok=True)
