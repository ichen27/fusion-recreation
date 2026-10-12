"""Compare disposable exact flat-face probe with real OCCT through OCP."""
import json, time, platform, importlib.metadata
from pathlib import Path
from fractions import Fraction as F
from kernel import Solid, intersect, subtract, union, volume, total_volume, validate
from OCP.gp import gp_Pnt
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace, BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopoDS import TopoDS
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp

def occt_shape(s):
    sew=BRepBuilderAPI_Sewing()
    for f in s.faces:
        polygon=BRepBuilderAPI_MakePolygon()
        for p in f: polygon.Add(gp_Pnt(*map(float,p)))
        polygon.Close()
        face=BRepBuilderAPI_MakeFace(polygon.Wire())
        if not face.IsDone(): raise RuntimeError("OCCT face construction failed")
        sew.Add(face.Face())
    sew.Perform()
    shape=BRepBuilderAPI_MakeSolid(TopoDS.Shell(sew.SewedShape())).Solid()
    if not BRepCheck_Analyzer(shape).IsValid(): raise RuntimeError("Invalid OCCT input")
    return shape

def measure(s):
    props=GProp_GProps(); BRepGProp.VolumeProperties_s(s,props)
    return props.Mass()

a=Solid.box((-1,-1,-1),(1,1,1))
cases=[
 ("overlap",Solid.box((0,0,0),(4,4,4)),Solid.box((2,1,1),(6,3,3)),False),
 ("containment",Solid.box((0,0,0),(4,4,4)),Solid.box((1,1,1),(3,3,3)),False),
 ("identical",a,a,False),
 ("touch_face",a,Solid.box((1,-1,-1),(3,1,1)),False),
 ("separated",a,Solid.box((2,-1,-1),(3,1,1)),False),
 ("diamond",Solid.extrude([(0,-1),(1,0),(0,1),(-1,0)],2),Solid.box((0,0,0),(1,1,2)),False),
 ("rotated",a,a.affine(((F(3,5),-F(4,5),0),(F(4,5),F(3,5),0),(0,0,1)),(0,0,0)),False),
 ("skewed",a,a.affine(((1,F(1,3),0),(0,1,F(2,7)),(0,0,1)),(F(1,5),F(2,3),F(-1,4))),False),
]
for digits in (3,6,8,12,30):
    e=F(1,10**digits)
    cases.append((f"thin_1e-{digits}",Solid.box((0,0,0),(1,1,1)),
                  Solid.box((1-e,0,0),(2,1,1)),True))
rows=[]
for name,left,right,stress in cases:
    x,y=occt_shape(left),occt_shape(right)
    for op,own,reference in (("intersection",lambda: [intersect(left,right)],BRepAlgoAPI_Common),
                             ("difference",lambda: subtract(left,right),BRepAlgoAPI_Cut),
                             ("union",lambda: union(left,right),BRepAlgoAPI_Fuse)):
        started=time.perf_counter(); cells=own(); exact=total_volume(cells); own_ms=(time.perf_counter()-started)*1000
        started=time.perf_counter(); builder=reference(x,y); builder.Build(); shape=builder.Shape()
        occt_ms=(time.perf_counter()-started)*1000; actual=measure(shape)
        abs_error=abs(float(exact)-actual)
        rows.append(dict(case=name,operation=op,stress=stress,exact=str(exact),exact_float=float(exact),
                         occt_volume=actual,abs_error=abs_error,relative_error=abs_error/float(exact) if exact else None,
                         within_volume_tolerance=abs_error<=max(1e-6,abs(float(exact))*1e-8),
                         occt_done=builder.IsDone(),occt_valid=BRepCheck_Analyzer(shape).IsValid(),
                         exact_cells_valid=all(not validate(c) for c in cells),
                         exact_ms=own_ms,occt_ms=occt_ms,output_cells=len(cells),
                         max_rational_bits=max((max(v.numerator.bit_length(),v.denominator.bit_length()) for c in cells for f in c.faces for p in f for v in p),default=0)))
report=dict(platform=platform.platform(),python=platform.python_version(),
            ocp_package=importlib.metadata.version("cadquery-ocp"),
            note="Exploratory single-run timings; input conversion excluded. Exact convex cells versus OCCT merged B-rep; not equal work. Stress cases deliberately probe tolerance/float limits; no claim of overall superiority.",
            rows=rows)
Path("comparison.json").write_text(json.dumps(report,indent=2)+"\n")
normal=[r for r in rows if not r["stress"]]
assert all(r["occt_done"] and r["occt_valid"] and r["exact_cells_valid"] and r["within_volume_tolerance"] for r in normal)
print(json.dumps({"normal_comparisons":len(normal),"normal_passed":len(normal),
                  "max_normal_error":max(r["abs_error"] for r in normal),
                  "stress_intersections":[r for r in rows if r["stress"] and r["operation"]=="intersection"]},indent=2))
