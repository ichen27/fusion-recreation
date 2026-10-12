import json,os,select,signal,subprocess,sys,tempfile,time,unittest
RUNNER=sys.argv.pop(1)
def sketch(width=40):
 return {"entities":[{"type":"line","id":"b","a":[0,0],"b":[width,0],"construction":False},
 {"type":"line","id":"r","a":[width,0],"b":[width,20],"construction":False},
 {"type":"line","id":"t","a":[width,20],"b":[0,20],"construction":False},
 {"type":"line","id":"l","a":[0,20],"b":[0,0],"construction":False}],"constraints":[]}
def command(tx="t1",rev=0):
 return {"documentId":"doc","expectedRevision":rev,"transactionId":tx,"operation":"CreateSketch","parameters":{"featureId":"s","sketch":sketch()}}
class Client:
 def __init__(self,path,test=False):
  self.p=subprocess.Popen([RUNNER,"--store",path,"--document","doc"]+(["--allow-test-faults"] if test else []),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.buffer=b""
 def send(self,kind,**kwargs):
  self.raw(json.dumps({"protocolVersion":1,"kind":kind,**kwargs}))
 def raw(self,line):self.p.stdin.write(line.encode()+b"\n");self.p.stdin.flush()
 def read(self):
  deadline=time.monotonic()+15
  while b"\n" not in self.buffer:
   left=deadline-time.monotonic()
   if left<=0:raise AssertionError("runner response timeout")
   if not select.select([self.p.stdout],[],[],left)[0]:raise AssertionError("runner response timeout")
   data=os.read(self.p.stdout.fileno(),65536)
   if not data:raise AssertionError("runner exited: "+self.p.stderr.read().decode())
   self.buffer+=data
  line,self.buffer=self.buffer.split(b"\n",1)
  return json.loads(line)
 def close(self):
  if self.p.poll() is None:
   self.p.stdin.close()
   try:self.p.wait(timeout=5)
   except subprocess.TimeoutExpired:self.p.kill();self.p.wait()
  self.p.stdout.close();self.p.stderr.close()
class Runner(unittest.TestCase):
 def test_disconnect_with_large_diagnostic_reaps_worker(self):
  with tempfile.TemporaryDirectory() as path:
   p=subprocess.Popen([RUNNER,"--store",path,"--document","doc"],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
   try:
    cmd=command();cmd["parameters"]["sketch"]["entities"][0]["id"]="bad:"+("x"*131072)
    p.stdin.write((json.dumps({"protocolVersion":1,"kind":"commit","command":cmd})+"\n").encode());p.stdin.close()
    self.assertEqual(p.wait(timeout=4),0)
   finally:
    if p.poll() is None:os.killpg(p.pid,signal.SIGKILL);p.wait()

 def test_writers_restart_validation_and_previews(self):
  with tempfile.TemporaryDirectory() as path:
   a,b=Client(path),Client(path)
   try:
    a.send("commit",command=command("a"));b.send("commit",command=command("b"))
    replies=[a.read(),b.read()]
    self.assertEqual(sum(r["ok"] for r in replies),1)
    self.assertEqual(next(r for r in replies if not r["ok"])["error"]["code"],"RevisionConflict")
    winner="a" if replies[0]["ok"] else "b"
   finally:a.close();b.close()
   c=Client(path,True)
   try:
    c.send("commit",command=command(winner));r=c.read();self.assertTrue(r["ok"]);self.assertEqual(r["revision"],1)
    for raw,code in [('not json',"InvalidMessage"),('{"protocolVersion":2,"kind":"snapshot"}',"UnsupportedProtocol")]:
     c.raw(raw);self.assertEqual(c.read()["error"]["code"],code)
    for value in [-1,1.5,"1",True]:
     cmd=command("invalid");cmd["expectedRevision"]=value
     c.send("commit",command=cmd);self.assertEqual(c.read()["error"]["code"],"InvalidMessage")
    bad=command("numeric",1);bad["operation"]="Extrude";bad["parameters"]={"featureId":"e","profileId":"s","depth":True}
    c.send("commit",command=bad);self.assertEqual(c.read()["error"]["code"],"InvalidMessage")
    preview=command("valid-preview",1);preview["parameters"]["featureId"]="temporary"
    c.send("preview",jobId="completed",command=preview)
    self.assertEqual(c.read()["kind"],"accepted")
    result=c.read();self.assertTrue(result["ok"]);self.assertEqual(result["kind"],"previewResult")
    self.assertEqual(result["revision"],1);self.assertEqual(result["proposedRevision"],2)
    c.send("snapshot");self.assertEqual(c.read()["revision"],1)
    c.send("preview",jobId="preview",command=command("p",1),testStopWorker=True)
    self.assertEqual(c.read()["kind"],"accepted")
    c.send("cancel",jobId="preview");self.assertEqual(c.read()["kind"],"cancelled")
    c.send("snapshot");self.assertEqual(c.read()["revision"],1)
    c.send("preview",jobId="disconnect",command=command("q",1),testStopWorker=True)
    self.assertEqual(c.read()["kind"],"accepted")
   finally:c.close()
   d=Client(path)
   try:d.send("snapshot");self.assertEqual(d.read()["revision"],1)
   finally:d.close()
if __name__=="__main__":unittest.main()
