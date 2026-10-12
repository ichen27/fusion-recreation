"""Collect measured Gate 0 evidence; skipped references never count as passed."""
import argparse,json,math,platform,resource,shutil,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from native_client import Client,rectangle

def reference_passed(result):
    return result.get("status")=="passed"

def scenario(build):
    directory=Path(tempfile.mkdtemp(prefix="foundation-evidence-",dir=build))
    store=directory/"document";latencies={}
    with Client(build/"cad-runner",store) as client:
        def commit(operation,parameters,revision,tx):
            result,ms=client.request("commit",command={"documentId":"document","expectedRevision":revision,
                "transactionId":tx,"operation":operation,"parameters":parameters})
            if result["revision"]!=revision+1:raise RuntimeError("Unexpected committed revision")
            latencies[tx]=ms
        commit("CreateSketch",{"featureId":"sketch","sketch":rectangle()},0,"create")
        commit("Extrude",{"featureId":"extrude","profileId":"sketch","depth":10},1,"extrude")
        commit("Hole",{"featureId":"hole","baseFeatureId":"extrude","radius":3,"centerMode":0,
               "support":{"featureId":"extrude","role":"top","evolutionIds":["extrude/top"]}},2,"hole")
        before,_=client.request("snapshot")
        commit("EditSketch",{"featureId":"sketch","sketch":rectangle(50)},3,"edit")
        after,_=client.request("snapshot")
    with Client(build/"cad-runner",store) as reopened:
        restored,ms=reopened.request("snapshot");latencies["reopenSnapshot"]=ms
        step=directory/"edited.step"
        _,ms=reopened.request("exportStep",path=str(step));latencies["exportStep"]=ms
    native=subprocess.run([str(build/"cad-inspect"),str(step)],text=True,capture_output=True,check=True)
    imported=json.loads(native.stdout.strip().splitlines()[-1])
    hole=lambda snap:next(b["volume"] for b in snap["bodies"] if b["featureId"]=="hole")
    errors={"initialVolume":abs(hole(before)-(8000-90*math.pi)),
            "editedVolume":abs(hole(after)-(10000-90*math.pi)),
            "reopenedVolume":abs(hole(restored)-hole(after)),
            "stepVolume":abs(imported["volume"]-hole(after))}
    if any(error>1e-6 for error in errors.values()):raise RuntimeError("Analytic volume fixture failed: "+str(errors))
    if restored["revision"]!=4 or [f["id"] for f in restored["document"]["features"]]!=["sketch","extrude","hole"]:
        raise RuntimeError("Revision or feature IDs changed after reopen")
    return {"status":"passed","absoluteErrorsMm3":errors,"latencyMs":latencies,"artifacts":str(directory)}

def collect(root,build,output,execute=subprocess.run):
    started=time.perf_counter()
    def capture(args):
        r=execute(args,cwd=root,text=True,capture_output=True)
        return (r.stdout or r.stderr).strip() if r.returncode==0 else "unavailable"
    freecad=shutil.which("FreeCADCmd") or shutil.which("freecadcmd")
    report={"sourceCommit":capture(["git","rev-parse","HEAD"]),
        "sourceDirty":bool(capture(["git","status","--porcelain"])),
        "platform":platform.platform(),
        "tools":{"compiler":capture(["c++","--version"]),"cmake":capture(["cmake","--version"]),
                 "ninja":capture(["ninja","--version"]),"python":sys.version},
        "dependencies":json.loads((root/"deps/lock.json").read_text()),
        "references":{"freecad":{"status":"unperformed","executable":freecad,
            "reason":"FreeCADCmd unavailable" if not freecad else "Executable detected; isolated reference workflow has not been validated"},
            "fusion":{"status":"unobserved","reason":"No dedicated fresh Fusion reference document was exercised on the mini"}},
        "foundation":{"status":"failed"}}
    tests=execute(["ctest","--test-dir",str(build),"--output-on-failure"],cwd=root,text=True,capture_output=True)
    report["ctest"]={"exitCode":tests.returncode,"output":tests.stdout+tests.stderr}
    code=tests.returncode
    if code==0:
        try:
            report["scenario"]=scenario(build)
            report["foundation"]={"status":"passed","decision":"conditional-go",
                "scope":"Headless bounded foundation only; not full CAD application or Fusion parity",
                "riskDecisions":["Line-loop extrusion and centered through holes only; arcs and circular extrusion reject explicitly",
                    "Semantic naming covers unique top support only; general split/deletion repair remains open",
                    "Immutable local snapshots use file locks, checksums and fsync; power-loss/filesystem guarantees are not exhaustively proven",
                    "Reference-application comparisons remain incomplete and cannot count as passed"]}
        except Exception as exc:
            code=1;report["scenario"]={"status":"failed","error":str(exc)}
    report["elapsedSeconds"]=time.perf_counter()-started
    peak=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report["peakChildRssBytes"]=peak if sys.platform=="darwin" else peak*1024
    report["memoryMeasurement"]="Maximum resident set of any waited-for child; not aggregate process-tree memory"
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+"\n")
    return (0 if code==0 else 1),report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--build",type=Path,default=Path("build"))
    parser.add_argument("--output",type=Path,default=Path("build/foundation-report.json"))
    args=parser.parse_args()
    code,report=collect(Path(__file__).resolve().parents[1],args.build.resolve(),args.output.resolve())
    print(json.dumps({"status":report["foundation"]["status"],"report":str(args.output)}))
    return code
if __name__=="__main__":sys.exit(main())
