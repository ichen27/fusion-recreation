"""OCCT boundary comparison: volume, area, validity, bidirectional surface samples."""
import json,platform,time,importlib.metadata
from pathlib import Path
from boundary import Body
from fixtures import workflows
from OCP.gp import gp_Pnt,gp_Dir,gp_Pln,gp_Pnt2d
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon,BRepBuilderAPI_MakeFace,BRepBuilderAPI_MakeSolid,BRepBuilderAPI_Sewing,BRepBuilderAPI_MakeVertex
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common,BRepAlgoAPI_Cut,BRepAlgoAPI_Fuse
from OCP.BRep import BRep_Builder,BRep_Tool
from OCP.TopoDS import TopoDS,TopoDS_Compound
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE,TopAbs_VERTEX,TopAbs_EDGE,TopAbs_IN
from OCP.BRepAdaptor import BRepAdaptor_Curve,BRepAdaptor_Surface
from OCP.BRepTools import BRepTools
from OCP.BRepClass import BRepClass_FaceClassifier

def wire(loop):
    p=BRepBuilderAPI_MakePolygon()
    for xyz in loop: p.Add(gp_Pnt(*map(float,xyz)))
    p.Close()
    if not p.IsDone(): raise RuntimeError("Failed wire construction")
    return p.Wire()

def simple_solid(s):
    sewing=BRepBuilderAPI_Sewing()
    for f in s.faces: sewing.Add(BRepBuilderAPI_MakeFace(wire(f)).Face())
    sewing.Perform()
    shape=BRepBuilderAPI_MakeSolid(TopoDS.Shell(sewing.SewedShape())).Solid()
    if not BRepCheck_Analyzer(shape).IsValid(): raise RuntimeError("Invalid reference input")
    return shape

def compound(shapes):
    builder=BRep_Builder(); result=TopoDS_Compound(); builder.MakeCompound(result)
    for s in shapes: builder.Add(result,s)
    return result

def faces_of(shape):
    ex=TopExp_Explorer(shape,TopAbs_FACE); result=[]
    while ex.More():
        result.append(TopoDS.Face(ex.Current())); ex.Next()
    return result

def merged_faces(boundary):
    result=[]
    for f in boundary.faces:
        plane=gp_Pln(gp_Pnt(*map(float,f.outer[0])),gp_Dir(*map(float,f.normal)))
        builder=BRepBuilderAPI_MakeFace(plane,wire(f.outer),True)
        for hole in f.holes: builder.Add(wire(hole))
        if not builder.IsDone(): raise RuntimeError("Failed merged face construction")
        face=builder.Face()
        if not BRepCheck_Analyzer(face).IsValid(): raise RuntimeError("Invalid merged face")
        result.append(face)
    return result

def measure(shape,kind):
    props=GProp_GProps()
    if kind=="volume": BRepGProp.VolumeProperties_s(shape,props)
    else: BRepGProp.SurfaceProperties_s(shape,props)
    return props.Mass()

def sample_faces(faces):
    points={}
    def put(p): points[(p.X(),p.Y(),p.Z())]=p
    for f in faces:
        vertices=TopExp_Explorer(f,TopAbs_VERTEX)
        while vertices.More():
            put(BRep_Tool.Pnt_s(TopoDS.Vertex(vertices.Current()))); vertices.Next()
        edges=TopExp_Explorer(f,TopAbs_EDGE)
        while edges.More():
            curve=BRepAdaptor_Curve(TopoDS.Edge(edges.Current()))
            put(curve.Value((curve.FirstParameter()+curve.LastParameter())/2)); edges.Next()
        u0,u1,v0,v1=BRepTools.UVBounds_s(f); surface=BRepAdaptor_Surface(f)
        for s in (.2,.5,.8):
            for t in (.2,.5,.8):
                u=u0+s*(u1-u0); v=v0+t*(v1-v0)
                if BRepClass_FaceClassifier(f,gp_Pnt2d(u,v),1e-9).State()==TopAbs_IN:
                    put(surface.Value(u,v))
    return list(points.values())

def max_distance(points,surfaces):
    maximum=0.
    for p in points:
        check=BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(p).Vertex(),surfaces)
        check.Perform()
        if not check.IsDone(): raise RuntimeError("Surface distance failed")
        maximum=max(maximum,check.Value())
    return maximum

def run():
    rows=[]
    operations={"cut":BRepAlgoAPI_Cut,"union":BRepAlgoAPI_Fuse,"intersection":BRepAlgoAPI_Common}
    for name,initial,steps in workflows():
        body=Body.from_solid(initial); reference=simple_solid(initial)
        for step,(operation,tool) in enumerate(steps,1):
            started=time.perf_counter()
            body=getattr(body,operation)(Body.from_solid(tool))
            own_seconds=time.perf_counter()-started
            native=operations[operation](reference,simple_solid(tool)); native.Build()
            if not native.IsDone(): raise RuntimeError("Reference Boolean failed")
            reference=native.Shape()
            custom_faces=merged_faces(body.boundary); ref_faces=faces_of(reference)
            custom_surface=compound(custom_faces); ref_surface=compound(ref_faces)
            custom_points=sample_faces(custom_faces); ref_points=sample_faces(ref_faces)
            forward=max_distance(custom_points,ref_surface); reverse=max_distance(ref_points,custom_surface)
            volume=float(body.volume()); area=body.boundary.area()
            ref_volume=measure(reference,"volume"); ref_area=measure(reference,"area")
            row=dict(workflow=name,step=step,operation=operation,
                     cell_count=len(body.cells),merged_faces=len(body.boundary.faces),
                     holes=sum(len(f.holes) for f in body.boundary.faces),
                     shells=len(body.boundary.shells()),euler=body.boundary.euler_characteristics(),
                     volume=volume,reference_volume=ref_volume,volume_error=abs(volume-ref_volume),
                     area=area,reference_area=ref_area,area_error=abs(area-ref_area),
                     conversion_area_error=abs(measure(custom_surface,"area")-area),
                     boundary_volume_error=float(abs(body.boundary.volume()-body.volume())),
                     forward_surface_distance=forward,reverse_surface_distance=reverse,
                     custom_samples=len(custom_points),reference_samples=len(ref_points),
                     own_valid=not body.boundary.validate(),reference_valid=BRepCheck_Analyzer(reference).IsValid(),
                     build_seconds=own_seconds)
            row["passed"]=(row["own_valid"] and row["reference_valid"] and
                           row["volume_error"]<=max(1e-6,abs(volume)*1e-8) and
                           row["area_error"]<=max(1e-6,abs(area)*1e-8) and
                           row["conversion_area_error"]<=max(1e-6,abs(area)*1e-8) and
                           row["boundary_volume_error"]==0 and max(forward,reverse)<=1e-7)
            rows.append(row)
            print(name,step,"PASS" if row["passed"] else "FAIL",flush=True)
    report={"python":platform.python_version(),"platform":platform.platform(),
            "ocp_package":importlib.metadata.version("cadquery-ocp"),"rows":rows,
            "limits":"Sampled surface distances are not a proof of global boundary equality. Curves and general imported B-reps unsupported. Cell backing retained for repeated operations."}
    Path("boundary-comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    assert all(r["passed"] for r in rows)
    print(json.dumps({"comparisons":len(rows),"workflows":len(workflows()),
        "max_volume_error":max(r["volume_error"] for r in rows),
        "max_area_error":max(r["area_error"] for r in rows),
        "max_surface_distance":max(max(r["forward_surface_distance"],r["reverse_surface_distance"]) for r in rows),
        "total_surface_samples":sum(r["custom_samples"]+r["reference_samples"] for r in rows)},indent=2))

if __name__=="__main__": run()
