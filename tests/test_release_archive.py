"""Archive ownership must not disclose the build machine; bytes remain exact."""
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('kre_normalize_sdist', Path(__file__).resolve().parents[1] / 'scripts/normalize_sdist.py')
normalizer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(normalizer)

class ArchivePrivacyTests(unittest.TestCase):
    def test_normalized_headers_exact_payload_and_repeatability(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source.tar.gz'
            data = b'Synthetic source\n\nwith exact whitespace.\n'
            with tarfile.open(path, 'w:gz') as archive:
                info = tarfile.TarInfo('package/source.txt')
                info.size = len(data); info.uid = 123; info.gid = 456
                info.uname = 'synthetic-owner'; info.gname = 'synthetic-group'
                info.mtime = 123456789
                info.pax_headers = {'mtime': '123456789.5', 'atime': '123456780'}
                archive.addfile(info, io.BytesIO(data))
            normalizer.normalize(path)
            first = path.read_bytes()
            with tarfile.open(path) as archive:
                item = archive.getmembers()[0]
                self.assertEqual((item.uid,item.gid,item.uname,item.gname,item.mtime), (0,0,'','',0))
                self.assertEqual(item.pax_headers, {})
                self.assertEqual(archive.extractfile(item).read(), data)
            normalizer.normalize(path)
            self.assertEqual(first, path.read_bytes())

    def test_unsafe_archive_is_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            for name, kind in [('../escape',tarfile.REGTYPE),('package/link',tarfile.SYMTYPE)]:
                path = Path(temp) / 'source.tar.gz'
                with tarfile.open(path, 'w:gz') as archive:
                    item = tarfile.TarInfo(name);item.type = kind;item.linkname = 'elsewhere'
                    archive.addfile(item)
                before = path.read_bytes()
                with self.assertRaises(ValueError):normalizer.normalize(path)
                self.assertEqual(before,path.read_bytes())
