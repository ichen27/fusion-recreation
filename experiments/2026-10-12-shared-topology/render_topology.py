"""Render actual shared topology; meshing is for display only."""
from dataclasses import replace
import os
os.environ.setdefault("MPLCONFIGDIR",os.path.join(os.environ.get("TMPDIR","/tmp"),"fusion-matplotlib-cache"))
import vtk
from adapters import from_planar,from_curved
from compare_topology import native_faces
from kernel import Solid
from boundary import Body as Planar
from cylinders import Body as Curved
from curves import Rect,Disk
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopAbs import TopAbs_REVERSED
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

p=Planar.from_solid(Solid.box((-8,-5,0),(8,5,4)))
p=p.cut(Planar.from_solid(Solid.box((-4,-2,-1),(-1,2,5))))
p=from_planar(p)
c=Curved.extrude(Rect(-8,-5,8,5),0,4)
c=c.cut(Curved.extrude(Disk(-3,0,1.5),-1,5))
c=c.cut(Curved.extrude(Disk(-3,0,2.5),3,5))
c=c.cut(Curved.extrude(Disk(3,0,1.5),2,5))
c=from_curved(c)
top=next(i for i,f in enumerate(c.faces) if f.surface.kind=="plane" and
         f.surface.normal==(0,0,1) and f.surface.offset==4)
broken=replace(c,faces=c.faces[:top]+c.faces[top+1:])
assert not p.validate() and not c.validate()
assert "Open or nonmanifold edge" in broken.validate()
parts=[("Exact planar model",p),("Analytic curved model",c),("Missing top face",broken)]
window=vtk.vtkRenderWindow(); window.SetOffScreenRendering(1); window.SetSize(1800,560); window.SetMultiSamples(8)
for i,(title,boundary) in enumerate(parts):
    renderer=vtk.vtkRenderer(); renderer.SetViewport(i/3,0,(i+1)/3,1)
    renderer.SetBackground(244/255,246/255,248/255)
    for face,source in zip(native_faces(boundary),boundary.faces):
        points=vtk.vtkPoints(); polys=vtk.vtkCellArray()
        BRepMesh_IncrementalMesh(face,.008,False,.1,False)
        loc=TopLoc_Location(); mesh=BRep_Tool.Triangulation_s(face,loc)
        for j in range(1,mesh.NbTriangles()+1):
            ids=list(mesh.Triangle(j).Get())
            if face.Orientation()==TopAbs_REVERSED: ids.reverse()
            triangle=vtk.vtkTriangle()
            for k,node in enumerate(ids):
                point=mesh.Node(node).Transformed(loc.Transformation())
                triangle.GetPointIds().SetId(k,points.InsertNextPoint(point.X(),point.Y(),point.Z()))
            polys.InsertNextCell(triangle)
        data=vtk.vtkPolyData(); data.SetPoints(points); data.SetPolys(polys)
        clean=vtk.vtkCleanPolyData(); clean.SetInputData(data); clean.SetTolerance(1e-9)
        normals=vtk.vtkPolyDataNormals(); normals.SetInputConnection(clean.GetOutputPort())
        normals.ConsistencyOn(); normals.SetFeatureAngle(45)
        mapper=vtk.vtkPolyDataMapper(); mapper.SetInputConnection(normals.GetOutputPort())
        actor=vtk.vtkActor(); actor.SetMapper(mapper)
        actor.GetProperty().SetColor((.82,.59,.25) if source.surface.kind=="cylinder" else (.35,.64,.80))
        actor.GetProperty().SetAmbient(.28); actor.GetProperty().SetDiffuse(.72)
        renderer.AddActor(actor)
    # Draw the common analytic edges, not tessellation diagonals.
    points=vtk.vtkPoints(); lines=vtk.vtkCellArray()
    owners=boundary.owners()
    for edge_id,e in enumerate(boundary.edges):
        if edge_id not in owners: continue
        count=25 if e.curve.kind=="arc" else 2
        line=vtk.vtkPolyLine(); line.GetPointIds().SetNumberOfIds(count)
        for k in range(count):
            line.GetPointIds().SetId(k,points.InsertNextPoint(*map(float,e.curve.point(k/(count-1)))))
        lines.InsertNextCell(line)
    data=vtk.vtkPolyData(); data.SetPoints(points); data.SetLines(lines)
    mapper=vtk.vtkPolyDataMapper(); mapper.SetInputData(data)
    actor=vtk.vtkActor(); actor.SetMapper(mapper)
    actor.GetProperty().SetColor(.12,.20,.28); actor.GetProperty().SetLineWidth(1.3)
    renderer.AddActor(actor)
    camera=renderer.GetActiveCamera(); camera.SetPosition(17,-29,32); camera.SetFocalPoint(0,0,2)
    camera.SetViewUp(0,0,1); camera.ParallelProjectionOn(); camera.SetParallelScale(10.5)
    renderer.ResetCameraClippingRange(); window.AddRenderer(renderer)
window.Render()
capture=vtk.vtkWindowToImageFilter(); capture.SetInput(window); capture.ReadFrontBufferOff(); capture.Update()
writer=vtk.vtkPNGWriter(); writer.SetFileName("topology-render.png"); writer.SetInputConnection(capture.GetOutputPort()); writer.Write()
window.Finalize()
fig=plt.figure(figsize=(15,5.8),facecolor="#f4f6f8")
ax=fig.add_axes([0,.19,1,.64]); ax.imshow(mpimg.imread("topology-render.png")); ax.axis("off")
fig.suptitle("One boundary checker for flat faces and curved walls",fontsize=18,fontweight="bold",y=.97,color="#18283a")
for i,(title,boundary) in enumerate(parts):
    x=(i+.5)/3
    fig.text(x,.84,title,ha="center",fontsize=12,fontweight="bold",color="#18283a")
    text="VALID · every edge has two opposite uses" if i<2 else "REJECTED · open boundary edges"
    fig.text(x,.18,text,ha="center",fontsize=10,color="#28734c" if i<2 else "#ae3838",fontweight="bold")
fig.text(.5,.10,"Blue: plane faces   •   Gold: cylinder patches   •   Dark lines: shared analytic edges",
         ha="center",fontsize=11,color="#405568")
fig.text(.5,.04,"Research prototype. Common incidence validation; separate Boolean engines. OCCT tessellation is used only for display.",
         ha="center",fontsize=10,color="#65798b")
fig.savefig("shared-topology.png",dpi=140,facecolor=fig.get_facecolor())
print("Rendered shared topology and a deliberately broken boundary.")
