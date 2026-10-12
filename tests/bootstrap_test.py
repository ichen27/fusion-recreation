import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location("bootstrap",Path(__file__).resolve().parents[1]/"tools/bootstrap.py")
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
class ChecksumTests(unittest.TestCase):
 def test_corrupted_archive_is_rejected_before_extraction(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/"dependency.tar.gz";path.write_bytes(b"not an archive")
   with self.assertRaisesRegex(ValueError,"DependencyChecksumMismatch"):
    bootstrap.verify(path,"0"*64)
 def test_known_sha256(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/"text";path.write_bytes(b"abc")
   bootstrap.verify(path,"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
if __name__=="__main__":unittest.main()
