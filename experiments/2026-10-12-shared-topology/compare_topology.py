"""Compare the common analytic boundary with independent OCCT Boolean references."""
from pathlib import Path
import json
import math
from adapters import from_planar, from_curved
from topology import TAU
from kernel import Solid
from boundary import Body as Planar
from cylinders import Body as Curved
from fixtures import workflows as planar_workflows
from curved_fixtures import workflows as curved_workflows
import compare_boundary as helper
import compare_cylinders as curved_helper
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Ax3, gp_Circ, gp_Pln, gp_Cylinder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse, BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopoDS import TopoDS
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SHELL


def edge(curve):
    if curve.kind == "line":
        return BRepBuilderAPI_MakeEdge(gp_Pnt(*map(float,curve.p0)), gp_Pnt(*map(float,curve.p1))).Edge()
    circle = gp_Circ(gp_Ax2(gp_Pnt(*curve.center), gp_Dir(0,0,1)), curve.radius)
    lo, hi = sorted((curve.start,curve.start+curve.sweep))
    result = BRepBuilderAPI_MakeEdge(circle,lo,hi).Edge()
    return result if curve.sweep > 0 else TopoDS.Edge(result.Reversed())


def wire(boundary, loop):
    builder = BRepBuilderAPI_MakeWire()
    for use in loop:
        builder.Add(edge(boundary.directed(use)[2]))
    if not builder.IsDone():
        raise RuntimeError("Shared boundary wire conversion failed")
    return builder.Wire()


def native_faces(boundary):
    result = []
    for face in boundary.faces:
        surface = face.surface
        if surface.kind == "plane":
            n = tuple(map(float,surface.normal))
            nn = sum(x*x for x in n)
            point = tuple(float(surface.offset)*x/nn for x in n)
            plane = gp_Pln(gp_Pnt(*point),gp_Dir(*n))
            builder = BRepBuilderAPI_MakeFace(plane,wire(boundary,face.loops[0]),True)
            for loop in face.loops[1:]:
                builder.Add(wire(boundary,loop))
            native = builder.Face()
        else:
            cylinder = gp_Cylinder(gp_Ax3(gp_Pnt(*surface.center,0),gp_Dir(0,0,1)), surface.radius)
            # A 3D wire alone has no cylinder p-curves. Current wall patches
            # are rectangles in angle/z; derive and verify that domain explicitly.
            if len(face.loops) != 1:
                raise RuntimeError("Cylinder export requires a rectangular patch")
            uv = []
            for use in face.loops[0]:
                p = boundary.directed(use)[2].p0
                angle = math.atan2(p[1]-surface.center[1],p[0]-surface.center[0])
                angle = surface.angle_origin+(angle-surface.angle_origin+math.pi)%TAU-math.pi
                uv.append((angle,p[2]))
            u0,u1 = min(p[0] for p in uv),max(p[0] for p in uv)
            z0,z1 = min(p[1] for p in uv),max(p[1] for p in uv)
            angular_tol = boundary.tolerance/surface.radius
            if any(min(abs(u-u0),abs(u-u1)) > angular_tol*4 and
                   min(abs(z-z0),abs(z-z1)) > boundary.tolerance*4 for u,z in uv):
                raise RuntimeError("Cylinder trim is not rectangular")
            uv_area = abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(uv,uv[1:]+uv[:1])))/2
            if abs(uv_area-(u1-u0)*(z1-z0))*surface.radius > 1e-7:
                raise RuntimeError("Cylinder trim area mismatch")
            builder = BRepBuilderAPI_MakeFace(cylinder,u0,u1,z0,z1)
            native = builder.Face()
            if surface.orientation < 0:
                native = TopoDS.Face(native.Reversed())
        if not builder.IsDone() or not BRepCheck_Analyzer(native).IsValid():
            raise RuntimeError("Invalid shared analytic face conversion")
        result.append(native)
    return result


def shell_count(shape):
    explorer = TopExp_Explorer(shape,TopAbs_SHELL)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def compare(name, step, boundary, reference):
    own = native_faces(boundary)
    refs = helper.faces_of(reference)
    own_surface, ref_surface = helper.compound(own), helper.compound(refs)
    a, b = helper.sample_faces(own), helper.sample_faces(refs)
    forward = helper.max_distance(a,ref_surface)
    reverse = helper.max_distance(b,own_surface)
    sewing = BRepBuilderAPI_Sewing(1e-7)
    for face in own:
        sewing.Add(face)
    sewing.Perform()
    sewn = sewing.SewedShape()
    row = {"workflow":name,"step":step,**boundary.summary(),
           "reference_valid":bool(BRepCheck_Analyzer(reference).IsValid()),
           "converted_valid":bool(BRepCheck_Analyzer(sewn).IsValid()),
           "reference_shells":shell_count(reference), "converted_shells":shell_count(sewn),
           "area_error_mm2":abs(helper.measure(own_surface,"area")-helper.measure(reference,"area")),
           "volume_error_mm3":abs(helper.measure(sewn,"volume")-helper.measure(reference,"volume")),
           "forward_distance_mm":forward,"reverse_distance_mm":reverse,
           "surface_samples":len(a)+len(b)}
    row["passed"] = (not row["errors"] and row["reference_valid"] and row["converted_valid"] and
                     row["shells"] == row["reference_shells"] == row["converted_shells"] and
                     row["area_error_mm2"] < 1e-6 and row["volume_error_mm3"] < 1e-6 and
                     max(forward,reverse) < 1e-7)
    return row


def run():
    operations = {"cut":BRepAlgoAPI_Cut,"union":BRepAlgoAPI_Fuse,"intersection":BRepAlgoAPI_Common}
    rows = []
    for backend, workflows, create, convert, native in (
        ("planar",planar_workflows,Planar.from_solid,from_planar,helper.simple_solid),
        ("curved",curved_workflows,lambda spec:Curved.extrude(*spec),from_curved,curved_helper.native_primitive)):
        for name,initial,steps in workflows():
            body, reference = create(initial), native(initial)
            if not steps:
                rows.append(compare(backend+"/"+name,0,convert(body),reference))
            for step,(op,tool) in enumerate(steps,1):
                body = getattr(body,op)(create(tool))
                operation = operations[op](reference,native(tool))
                if not operation.IsDone():
                    raise RuntimeError("OCCT reference Boolean failed")
                reference = operation.Shape()
                row = compare(backend+"/"+name,step,convert(body),reference)
                rows.append(row)
                print(row["workflow"],step,row["passed"],flush=True)
    report = {"rows":rows,"comparisons":len(rows),"passed":all(r["passed"] for r in rows),
              "surface_samples":sum(r["surface_samples"] for r in rows),
              "max_area_error_mm2":max(r["area_error_mm2"] for r in rows),
              "max_volume_error_mm3":max(r["volume_error_mm3"] for r in rows),
              "max_surface_distance_mm":max(max(r["forward_distance_mm"],r["reverse_distance_mm"]) for r in rows),
              "limits":"Finite surface samples and shell counts are not a proof of global equivalence."}
    Path("topology-comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},indent=2))
    assert report["passed"]


if __name__ == "__main__":
    run()
