"""Verify an explicit public source manifest and basic publication red flags.

This is a lightweight release check, not a complete secret detector. Review the
allowlist and artifacts separately. It never prints matched content.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

PATTERNS = {
    'credential_signature': re.compile(rb'(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{25,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)'),
    'personal_filesystem_path': re.compile(rb'/Users/[A-Za-z0-9._-]+|/home/[A-Za-z0-9._-]+|[A-Z]:\\Users\\[A-Za-z0-9._-]+'),
}
# Deliberately fictional privacy-negative fixture, not a real user path.
SYNTHETIC_PATH = b'/Users/private-secret'


def files_from(root, names):
    result = {}
    for name in names:
        p = PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or not p.parts or '.git' in p.parts:
            raise ValueError('Invalid manifest path')
        q = root.joinpath(*p.parts)
        if not q.is_file() or q.is_symlink() or not q.resolve().is_relative_to(root):
            raise ValueError('Manifest file missing or unsafe')
        if name in result:
            raise ValueError('Duplicate manifest path')
        result[name] = q.read_bytes()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--manifest', type=Path, default=Path('PUBLIC_SOURCE_SHA256.json'))
    p.add_argument('--write-from', type=Path, help='explicit reviewed file list; creates a new manifest only')
    args = p.parse_args()
    root = args.root.resolve()
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    if args.write_from:
        if manifest.exists():
            raise ValueError('Refusing to overwrite an existing manifest')
        names = [n for n in args.write_from.read_text().splitlines() if n]
        files = files_from(root, names)
        data = {'format': 'kre-public-source-manifest/1', 'files': {
            n: hashlib.sha256(b).hexdigest() for n, b in sorted(files.items())}}
        manifest.write_text(json.dumps(data, indent=2) + '\n')
    data = json.loads(manifest.read_text())
    if data.get('format') != 'kre-public-source-manifest/1' or not isinstance(data.get('files'), dict):
        raise ValueError('Unrecognized manifest')
    files = files_from(root, data['files'])
    failures = []
    for name, raw in files.items():
        if hashlib.sha256(raw).hexdigest() != data['files'][name]:
            failures.append({'path': name, 'kind': 'hash_mismatch'})
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(raw):
                if (kind == 'personal_filesystem_path' and match.group() == SYNTHETIC_PATH
                        and name in {'tests/test_quality.py', 'scripts/release_check.py'}):
                    continue
                failures.append({'path': name, 'kind': kind})
                break
    # Public Git may contain only the explicit source files and the manifest.
    if (root / '.git').exists():
        tracked = set(subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')) - {''}
        allowed = set(files) | {manifest.relative_to(root).as_posix()}
        failures.extend({'path': n, 'kind': 'unmanifested_tracked_file'} for n in sorted(tracked - allowed))
    print(json.dumps({'files_checked': len(files), 'findings': failures, 'passed': not failures,
                      'scope': 'Explicit source manifest and signatures; artifact and human review remain required.'}, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, subprocess.SubprocessError):
        print('release-check: invalid or unavailable source manifest', file=sys.stderr)
        raise SystemExit(2)
