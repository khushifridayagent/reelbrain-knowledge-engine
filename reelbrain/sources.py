"""Public Instagram URL gate and text/export input adapters.

Parsing a URL is not permission to download or scrape its media.
"""
import re
from urllib.parse import urlsplit
from .contracts import Observation

class InvalidSource(ValueError): pass

_IG_LINK = re.compile(r'https?://(?:www\.)?instagram\.com/(?:p|reel|reels|tv)/[A-Za-z0-9_-]+/?(?:\?[^\s<]*)?', re.I)
_SHORTCODE = re.compile(r'^/(p|reel|reels|tv)/([A-Za-z0-9_-]+)/?$')

def canonicalize_instagram(value: str) -> str:
    try: parts=urlsplit(value.strip())
    except ValueError as exc: raise InvalidSource('malformed URL') from exc
    if parts.scheme!='https' or (parts.hostname or '').lower() not in {'instagram.com','www.instagram.com'}:
        raise InvalidSource('must be an HTTPS public Instagram post URL')
    if parts.username or parts.password or parts.port not in (None,443):
        raise InvalidSource('credential/port not permitted')
    match=_SHORTCODE.fullmatch(parts.path)
    if not match: raise InvalidSource('not a valid post/reel path')
    kind='reel' if match.group(1) in ('reels','reel') else match.group(1)
    return f'https://www.instagram.com/{kind}/{match.group(2)}/'

def extract_instagram_urls(text: str) -> list[str]:
    seen=set();out=[]
    for match in _IG_LINK.finditer(text):
        try: url=canonicalize_instagram(match.group(0).rstrip(').,;!?'))
        except InvalidSource:continue
        if url not in seen:seen.add(url);out.append(url)
    return out

def parse_saved_export(obj: object)-> list[str]:
    """Only yields links; a saved-post export provides no extracted media/content."""
    out=[];seen=set()
    def walk(x):
        if isinstance(x,dict):
            for v in x.values():walk(v)
        elif isinstance(x,list):
            for v in x:walk(v)
        elif isinstance(x,str):
            for url in extract_instagram_urls(x):
                if url not in seen:seen.add(url);out.append(url)
    walk(obj)
    return out

def parse_text(text: str, source: str='notes.txt')->list[Observation]:
    """Preserves verbatim source paragraphs with stable line evidence pointers."""
    blocks=[];chunk=[];start=1
    def flush():
        nonlocal chunk
        if chunk:
            content='\n'.join(chunk).strip()
            if content:blocks.append(Observation(content,kind='document',locator=f'{source}:L{start}'))
            chunk=[]
    for line_no,line in enumerate(text.splitlines(),1):
        if not line.strip():flush();continue
        if line.lstrip().startswith('#') and chunk:flush()
        if not chunk:start=line_no
        chunk.append(line)
    flush()
    return blocks


from dataclasses import dataclass

@dataclass(frozen=True)
class InstagramMention:
    """A pointer to user-submitted context, NOT proof of Reel contents."""
    canonical_url: str
    line: int
    char_offset: int
    context: str


def extract_instagram_mentions(text: str, *, context_lines: int = 1, max_context_chars: int = 650) -> list[InstagramMention]:
    """Preserve *each* link occurrence and its precise source line/offset.

    Comments alongside the link are user notes, never reclassified as speech,
    caption, OCR, creator claim, or independently verified repository evidence.
    """
    if not 0 <= context_lines <= 5:
        raise ValueError('context_lines must be between 0 and 5')
    if max_context_chars < 60:
        raise ValueError('max_context_chars too small')
    lines = text.splitlines(keepends=True)
    line_offsets = []
    cursor = 0
    for line in lines:
        line_offsets.append(cursor)
        cursor += len(line)
    mentions = []
    for i, line in enumerate(lines):
        for match in _IG_LINK.finditer(line):
            raw = match.group(0).rstrip(').,;!?\"\'')
            try:
                canonical = canonicalize_instagram(raw)
            except InvalidSource:
                continue
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            # Focus on the linked line when context is large, preserve others in
            # the immutable archive instead of pretending truncated notes are full.
            context = ''.join(lines[start:end]).strip()
            if len(context) > max_context_chars:
                context = context[:max_context_chars] + '… [context clipped; full archive retained]'
            mentions.append(InstagramMention(canonical, i + 1, line_offsets[i] + match.start(), context))
    return mentions
