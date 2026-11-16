"""Remove machine ownership/timestamps from an unpublished sdist, preserving payloads."""
import argparse
import copy
import gzip
from pathlib import Path, PurePosixPath
import os
import tarfile
import tempfile


def normalize(path):
    path = Path(path)
    temporary = None
    try:
        with tarfile.open(path, 'r:gz') as source:
            members = source.getmembers()
            if any(not (m.isfile() or m.isdir()) or PurePosixPath(m.name).is_absolute()
                   or '..' in PurePosixPath(m.name).parts for m in members):
                raise ValueError('Only relative regular-file/directory source archives are supported')
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.sdist-', delete=False) as raw:
                temporary = Path(raw.name)
                with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
                    with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as target:
                        for member in members:
                            clean = copy.copy(member)
                            clean.uid = clean.gid = clean.mtime = 0
                            clean.uname = clean.gname = ''
                            clean.pax_headers = {}
                            if member.isfile():
                                with source.extractfile(member) as payload:
                                    target.addfile(clean, payload)
                            else:
                                target.addfile(clean)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    args = parser.parse_args()
    for archive in args.archives:
        normalize(archive)
        print('Normalized archive ownership and timestamps:', archive.name)
