import os,signal,subprocess,sys,tempfile,time,unittest
from pathlib import Path
DRIVER=sys.argv.pop(1)
class Recovery(unittest.TestCase):
 def test_interrupt_and_disk_failure(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)
   subprocess.run([DRIVER,"initial",tmp],check=True)
   original=(p/"current.json").read_bytes()
   child=subprocess.Popen([DRIVER,"stop",tmp])
   try:
    deadline=time.monotonic()+10
    while not (p/"fault-ready").exists() and time.monotonic()<deadline:
     if child.poll() is not None:self.fail("save exited before fault point")
     time.sleep(.02)
    self.assertTrue((p/"fault-ready").exists())
    child.kill();child.wait(timeout=5)
   finally:
    if child.poll() is None:child.kill();child.wait()
   self.assertEqual((p/"current.json").read_bytes(),original)
   self.assertEqual(subprocess.check_output([DRIVER,"read",tmp]),b"1")
   self.assertNotEqual(subprocess.run([DRIVER,"fail",tmp]).returncode,0)
   self.assertEqual((p/"current.json").read_bytes(),original)
   self.assertEqual(subprocess.check_output([DRIVER,"read",tmp]),b"1")
if __name__=="__main__":unittest.main()
