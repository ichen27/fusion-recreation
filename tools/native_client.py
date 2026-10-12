"""Small JSON-lines client for local foundation fixtures (no network service)."""
import json,os,select,subprocess,time
class Client:
    def __init__(self,runner,store,document="document"):
        self.process=subprocess.Popen([str(runner),"--store",str(store),"--document",document],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.buffer=b""
    def request(self,kind,**fields):
        start=time.perf_counter()
        self.process.stdin.write((json.dumps({"protocolVersion":1,"kind":kind,**fields})+"\n").encode())
        self.process.stdin.flush()
        deadline=time.monotonic()+30
        while b"\n" not in self.buffer:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:
                raise RuntimeError("runner response timed out")
            chunk=os.read(self.process.stdout.fileno(),65536)
            if not chunk:raise RuntimeError("runner exited without a response")
            self.buffer+=chunk
        line,self.buffer=self.buffer.split(b"\n",1)
        result=json.loads(line)
        if not result.get("ok"):raise RuntimeError(str(result))
        return result,(time.perf_counter()-start)*1000
    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process.stdout.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def rectangle(width=40,height=20):
    vertices=[[0,0],[width,0],[width,height],[0,height]]
    names=["bottom","right","top","left"]
    entities=[{"type":"line","id":name,"a":vertices[i],"b":vertices[(i+1)%4],"construction":False}
              for i,name in enumerate(names)]
    constraints=[{"id":"join"+str(i),"kind":0,"entityIds":[name+":end",names[(i+1)%4]+":start"],"value":0}
                 for i,name in enumerate(names)]
    for name in names:
        constraints.append({"id":"direction-"+name,"kind":1 if name in ("bottom","top") else 2,"entityIds":[name],"value":0})
    constraints += [{"id":"origin","kind":5,"entityIds":["bottom:start"],"value":0},
                    {"id":"width","kind":3,"entityIds":["bottom"],"value":width},
                    {"id":"height","kind":3,"entityIds":["right"],"value":height}]
    return {"entities":entities,"constraints":constraints}
