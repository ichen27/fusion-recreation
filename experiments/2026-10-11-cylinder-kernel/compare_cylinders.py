"""Compare original analytic curves with independent OCCT 3D Boolean results."""
import sys,math,json,platform,importlib.metadata
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "2026-10-11-boundary-kernel"))
import compare_boundary as helper
from curves import Disk,Rect
from cylinders import Body
from curved_fixtures import workflows
from OCP.gp import gp_Pnt,gp_Ax2,gp_Dir,gp_Circ,gp_Vec,gp_Pln
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakePrism
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge,BRepBuilderAPI_MakeWire,BRepBuilderAPI_MakeFace
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Fuse,BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.TopAbs import TopAbs_IN
from OCP.TopoDS import TopoDS

def native_primitive(spec):
    profile,z0,z1=spec
    if isinstance(profile,Disk):
        return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(profile.x,profile.y,z0),gp_Dir(0,0,1)),profile.radius,z1-z0).Shape()
    return BRepPrimAPI_MakeBox(gp_Pnt(profile.x0,profile.y0,z0),profile.x1-profile.x0,profile.y1-profile.y0,z1-z0).Shape()

def native_edge(edge,z):
    if edge.kind=="line":
        return BRepBuilderAPI_MakeEdge(gp_Pnt(*edge.p0,z),gp_Pnt(*edge.p1,z)).Edge()
    circle=gp_Circ(gp_Ax2(gp_Pnt(*edge.center,z),gp_Dir(0,0,1)),edge.radius)
    if abs(abs(edge.sweep)-2*math.pi)<1e-10:
        result=BRepBuilderAPI_MakeEdge(circle).Edge()
    else:
        lo,hi=sorted((edge.start,edge.start+edge.sweep))
        result=BRepBuilderAPI_MakeEdge(circle,lo,hi).Edge()
    return result if edge.sweep>0 else TopoDS.Edge(result.Reversed())

def native_wire(loop,z):
    builder=BRepBuilderAPI_MakeWire()
    for edge in loop: builder.Add(native_edge(edge,z))
    if not builder.IsDone(): raise RuntimeError("Native wire conversion failed")
    return builder.Wire()

def cap_faces(cap):
    plane=gp_Pln(gp_Pnt(0,0,cap.z),gp_Dir(0,0,1))
    positives=[loop for loop in cap.region.loops if sum(e.area_integral for e in loop)>0]
    negatives=[loop for loop in cap.region.loops if sum(e.area_integral for e in loop)<0]
    builders=[BRepBuilderAPI_MakeFace(plane,native_wire(loop,cap.z),True) for loop in positives]
    raw=[builder.Face() for builder in builders]
    for hole in negatives:
        p=hole[0].point(.37); point=gp_Pnt(*p,cap.z)
        owners=[i for i,f in enumerate(raw) if BRepClass_FaceClassifier(f,point,1e-8).State()==TopAbs_IN]
        if not owners: raise RuntimeError("Cannot place cap hole")
        owner=min(owners,key=lambda i:sum(e.area_integral for e in positives[i]))
        builders[owner].Add(native_wire(hole,cap.z))
    result=[]
    for builder in builders:
        if not builder.IsDone(): raise RuntimeError("Native cap conversion failed")
        f=builder.Face()
        if not BRepCheck_Analyzer(f).IsValid(): raise RuntimeError("Invalid converted cap")
        result.append(f if cap.normal>0 else TopoDS.Face(f.Reversed()))
    return result

def custom_faces(body):
    faces=[]
    for wall in body.walls:
        prism=BRepPrimAPI_MakePrism(native_edge(wall.edge,wall.z0),gp_Vec(0,0,wall.z1-wall.z0))
        if not prism.IsDone(): raise RuntimeError("Native wall conversion failed")
        faces.extend(helper.faces_of(prism.Shape()))
    for cap in body.caps: faces.extend(cap_faces(cap))
    if not all(BRepCheck_Analyzer(f).IsValid() for f in faces): raise RuntimeError("Invalid converted wall")
    return faces

def compare(name,step,body,reference):
    custom=custom_faces(body); refs=helper.faces_of(reference)
    custom_surface=helper.compound(custom); ref_surface=helper.compound(refs)
    p=helper.sample_faces(custom); q=helper.sample_faces(refs)
    forward=helper.max_distance(p,ref_surface); reverse=helper.max_distance(q,custom_surface)
    rv=helper.measure(reference,"volume"); ra=helper.measure(reference,"area")
    row=dict(workflow=name,step=step,volume=body.volume,reference_volume=rv,
        volume_error=abs(body.volume-rv),area=body.area,reference_area=ra,
        area_error=abs(body.area-ra),conversion_area_error=abs(body.area-helper.measure(custom_surface,"area")),
        boundary_volume_error=abs(body.volume-body.boundary_volume),
        forward_surface_distance=forward,reverse_surface_distance=reverse,
        custom_samples=len(p),reference_samples=len(q),
        slabs=len(body.slabs),arc_walls=sum(w.edge.kind=="arc" for w in body.walls),
        own_consistency_passed=not body.validate(),reference_valid=BRepCheck_Analyzer(reference).IsValid())
    row["passed"]=(row["own_consistency_passed"] and row["reference_valid"] and
        row["volume_error"]<=max(1e-6,abs(rv)*1e-8) and row["area_error"]<=max(1e-6,abs(ra)*1e-8) and
        row["conversion_area_error"]<=max(1e-6,abs(ra)*1e-8) and
        row["boundary_volume_error"]<=max(1e-7,abs(rv)*1e-10) and max(forward,reverse)<=1e-7)
    return row

def run():
    rows=[]; operations={"cut":BRepAlgoAPI_Cut,"union":BRepAlgoAPI_Fuse,"intersection":BRepAlgoAPI_Common}
    for name,initial,steps in workflows():
        body=Body.extrude(*initial); reference=native_primitive(initial)
        if not steps:
            rows.append(compare(name,0,body,reference)); print(name,0,rows[-1]["passed"],flush=True)
        for step,(op,tool) in enumerate(steps,1):
            body=getattr(body,op)(Body.extrude(*tool))
            native=operations[op](reference,native_primitive(tool)); native.Build()
            if not native.IsDone(): raise RuntimeError("Native Boolean failure")
            reference=native.Shape(); rows.append(compare(name,step,body,reference))
            print(name,step,rows[-1]["passed"],flush=True)
    report={"python":platform.python_version(),"platform":platform.platform(),
            "ocp_package":importlib.metadata.version("cadquery-ocp"),"rows":rows,
            "limits":"Parallel axes only. Float64 tolerance policy with explicit rejection. Surface samples do not prove global equality; own validator checks loop and integral consistency, not general manifoldness."}
    Path("cylinder-comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    assert all(r["passed"] for r in rows)
    print(json.dumps({"workflows":len(workflows()),"comparisons":len(rows),
        "max_volume_error":max(r["volume_error"] for r in rows),
        "max_area_error":max(r["area_error"] for r in rows),
        "max_distance":max(max(r["forward_surface_distance"],r["reverse_surface_distance"]) for r in rows),
        "sample_evaluations":sum(r["custom_samples"]+r["reference_samples"] for r in rows)},indent=2))

if __name__=="__main__": run()
