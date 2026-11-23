"""Stage only safe source files for a new PRIVATE GitHub repository.

Does not authenticate, create, connect to or edit any GitHub repository.
"""
import argparse
import re
import shutil
from pathlib import Path, PurePosixPath

class StageError(ValueError):
    pass

DENY_PARTS = {'.git', '.venv', 'data', 'media', 'secrets', '__pycache__', '.pytest_cache'}
DENY_NAMES = {'.env', 'USER_PASTED_PROCEDURE_ORIGINAL.txt'}
DENY_SUFFIX = {'.db', '.sqlite', '.sqlite3', '.pem', '.key', '.p12', '.pfx', '.pyc'}
SECRET_PATTERNS = [
    re.compile(r'gh[pousr]_[a-zA-Z0-9]{24,}'),
    re.compile(r'github_pat_[a-zA-Z0-9_]{30,}'),
    re.compile(r'sk-proj-[a-zA-Z0-9_-]{30,}'),
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def review_files(root: Path, files: list[str]) -> list[str]:
    """Fail closed for private artifacts and conventional credential patterns."""
    root = root.resolve()
    reviewed = []
    for name in sorted(set(files)):
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise StageError(f'Unsafe relative path: {name}')
        if DENY_PARTS.intersection(path.parts) or path.name in DENY_NAMES or path.suffix.lower() in DENY_SUFFIX:
            raise StageError(f'Private or generated path cannot be staged: {name}')
        real = root.joinpath(*path.parts)
        if real.is_symlink() or not real.resolve().is_relative_to(root) or not real.is_file():
            raise StageError(f'Symlink, missing, or external path rejected: {name}')
        payload = real.read_bytes()
        if b'\x00' in payload or len(payload) > 2_000_000:
            raise StageError(f'Binary or unusually large file rejected: {name}')
        content = payload.decode('utf-8', errors='replace')
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            raise StageError(f'Potential credential detected in {name}')
        reviewed.append(name)
    return reviewed


def stage(root: Path, destination: Path) -> list[str]:
    root, destination = root.resolve(), destination.resolve()
    if destination == root or destination.is_relative_to(root):
        raise StageError('Staging destination must be outside source tree')
    if destination.exists():
        raise StageError('Staging destination already exists: no overwrite')
    candidates = []
    for path in root.rglob('*'):
        if not path.is_file() and not path.is_symlink():
            continue
        name = path.relative_to(root).as_posix()
        parts = PurePosixPath(name).parts
        if DENY_PARTS.intersection(parts) or path.name in DENY_NAMES or path.suffix.lower() in DENY_SUFFIX:
            continue
        candidates.append(name)
    accepted = review_files(root, candidates)
    destination.mkdir(parents=True, exist_ok=False)
    try:
        for name in accepted:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / name, target, follow_symlinks=False)
    except Exception:
        shutil.rmtree(destination)
        raise
    return accepted


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export safe files for a NEW private repo only')
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    result = stage(Path(__file__).resolve().parent.parent, args.destination)
    print(f'Locally staged {len(result)} source files to {args.destination} (nothing pushed)')
