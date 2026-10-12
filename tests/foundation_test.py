import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Foundation(unittest.TestCase):
 def module(self):
  spec=importlib.util.spec_from_file_location("collector",ROOT/"tools/verify_foundation.py")
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
 def test_skipped_reference_is_not_passed(self):
  m=self.module()
  self.assertFalse(m.reference_passed({"status":"unperformed"}))
  self.assertFalse(m.reference_passed({"status":"skipped"}))
  self.assertTrue(m.reference_passed({"status":"passed"}))
 def test_failed_check_fails_collector_and_records_versions(self):
  m=self.module()
  def execute(args,**kwargs):
   if args[0]=="ctest":return subprocess.CompletedProcess(args,1,"Intentional failing fixture","")
   return subprocess.CompletedProcess(args,0,"fixture version","")
  with tempfile.TemporaryDirectory() as tmp:
   code,report=m.collect(ROOT,Path(tmp),Path(tmp)/"report.json",execute=execute)
   self.assertNotEqual(code,0);self.assertEqual(report["foundation"]["status"],"failed")
   self.assertIn("sourceCommit",report);self.assertIn("dependencies",report);self.assertIn("compiler",report["tools"])
   self.assertNotEqual(report["references"]["freecad"]["status"],"passed")
   self.assertTrue((Path(tmp)/"report.json").exists())
if __name__=="__main__":unittest.main()
