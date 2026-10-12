"""Generate a visible curved-kernel demo and independently checked STEP export."""
import json,math
from pathlib import Path
from curves import Rect,Disk
from cylinders import Body
from compare_cylinders import custom_faces,helper
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing,BRepBuilderAPI_MakeSolid
from OCP.TopoDS import TopoDS
from OCP.BRepLib import BRepLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.STEPControl import STEPControl_Writer,STEPControl_Reader,STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

base=Body.extrude(Rect(-8,-5,8,5),0,4)
through=base.cut(Body.extrude(Disk(-3,0,1.5),-1,5))
blind=through.cut(Body.extrude(Disk(3,0,1.5),2,5))
bore=blind.cut(Body.extrude(Disk(-3,0,2.5),3,5))
overlap=base.cut(Body.extrude(Disk(-1,0,2),-1,5)).cut(Body.extrude(Disk(1,0,2),-1,5))
parts=[("Circular through-hole",through),("Add a blind hole",blind),
       ("Widen the first opening",bore),("Overlapping circular holes",overlap)]

# OCCT is an export adapter here: original profile/layer results define every face.
sew=BRepBuilderAPI_Sewing(1e-7)
for face in custom_faces(bore): sew.Add(face)
sew.Perform()
solid=BRepBuilderAPI_MakeSolid(TopoDS.Shell(sew.SewedShape())).Solid()
if not BRepLib.OrientClosedSolid_s(solid): raise RuntimeError("Cannot orient exported solid")
if not BRepCheck_Analyzer(solid).IsValid(): raise RuntimeError("Invalid export solid")
Interface_Static.SetCVal_s("write.step.unit","MM")
writer=STEPControl_Writer()
assert writer.Transfer(solid,STEPControl_AsIs)==IFSelect_RetDone
assert writer.Write("curved-kernel-demo.step")==IFSelect_RetDone
reader=STEPControl_Reader()
assert reader.ReadFile("curved-kernel-demo.step")==IFSelect_RetDone
assert reader.TransferRoots()>0
imported=reader.OneShape()
volume=helper.measure(imported,"volume"); area=helper.measure(imported,"area")
assert BRepCheck_Analyzer(imported).IsValid()
assert abs(volume-bore.volume)<=1e-6
assert abs(area-bore.area)<=1e-6
summary={"format":"STEP","units":"mm","export_adapter":"OCCT",
 "history_preserved":False,"reference":"original analytic profile/layer boundary",
 "expected_volume":bore.volume,"imported_volume":volume,
 "expected_area":bore.area,"imported_area":area,"imported_valid":True}
Path("step-roundtrip.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps(summary,indent=2),flush=True)

fig=plt.figure(figsize=(15,5.3),facecolor="#f4f6f8")
for index,(title,body) in enumerate(parts):
    ax=fig.add_subplot(1,4,index+1,projection="3d",facecolor="#f4f6f8")
    all_triangles=[]
    for face in custom_faces(body):
        BRepMesh_IncrementalMesh(face,.015,False,.16,False)
        loc=TopLoc_Location(); mesh=BRep_Tool.Triangulation_s(face,loc)
        triangles=[]
        for i in range(1,mesh.NbTriangles()+1):
            xyz=[]
            for node in mesh.Triangle(i).Get():
                p=mesh.Node(node).Transformed(loc.Transformation()); xyz.append([p.X(),p.Y(),p.Z()])
            triangles.append(xyz)
        all_triangles.extend(triangles)
    collection=Poly3DCollection(all_triangles,facecolors="#54a4cf" if index!=2 else "#d6a454",
        edgecolors=(0,0,0,0),linewidths=0,antialiased=False,shade=True)
    ax.add_collection3d(collection)
    ax.set(xlim=(-9,9),ylim=(-9,9),zlim=(-4.5,9.5))
    ax.set_box_aspect((1,1,14/18)); ax.view_init(elev=45,azim=-65); ax.set_axis_off()
    ax.set_title(title,fontsize=12,fontweight="bold",color="#18283a",pad=0)
    ax.text2D(.5,.04,f"Volume {body.volume:.3f} mm³",transform=ax.transAxes,ha="center",fontsize=10,color="#405568")
fig.suptitle("Custom kernel: analytic curves, blind holes and counterbores",fontsize=17,fontweight="bold",y=.97,color="#18283a")
fig.text(.5,.075,"First three panels show successive cuts on the same 16 × 10 × 4 mm block; fourth is a separate overlapping-hole example.",
         ha="center",fontsize=10,color="#405568")
fig.text(.5,.025,"Circle arcs and cylindrical walls define the models. Display tessellation and STEP export use OCCT.",ha="center",fontsize=10,color="#65798b")
fig.subplots_adjust(left=.015,right=.985,top=.87,bottom=.15,wspace=.03)
fig.savefig("cylinder-experiment.png",dpi=140,facecolor=fig.get_facecolor())
