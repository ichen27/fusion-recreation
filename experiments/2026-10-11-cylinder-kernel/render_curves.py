"""Depth-buffered illustration of the computed curved boundaries."""
import os
os.environ.setdefault("MPLCONFIGDIR",os.path.join(os.environ.get("TMPDIR", "/tmp"), "fusion-matplotlib-cache"))
import vtk
from curves import Disk,Rect
from cylinders import Body
from compare_cylinders import custom_faces
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopAbs import TopAbs_REVERSED
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

base=Body.extrude(Rect(-8,-5,8,5),0,4)
through=base.cut(Body.extrude(Disk(-3,0,1.5),-1,5))
blind=through.cut(Body.extrude(Disk(3,0,1.5),2,5))
bore=blind.cut(Body.extrude(Disk(-3,0,2.5),3,5))
overlap=base.cut(Body.extrude(Disk(-1,0,2),-1,5)).cut(Body.extrude(Disk(1,0,2),-1,5))
parts=[("Circular through-hole",through),("Add a blind hole",blind),
       ("Widen the first opening",bore),("Overlapping circular holes",overlap)]
window=vtk.vtkRenderWindow(); window.SetOffScreenRendering(1); window.SetSize(2100,550)
window.SetMultiSamples(8)
for i,(title,body) in enumerate(parts):
    points=vtk.vtkPoints(); polys=vtk.vtkCellArray()
    for face in custom_faces(body):
        BRepMesh_IncrementalMesh(face,.008,False,.10,False)
        loc=TopLoc_Location(); mesh=BRep_Tool.Triangulation_s(face,loc)
        for j in range(1,mesh.NbTriangles()+1):
            ids=list(mesh.Triangle(j).Get())
            if face.Orientation()==TopAbs_REVERSED: ids.reverse()
            triangle=vtk.vtkTriangle()
            for k,node in enumerate(ids):
                p=mesh.Node(node).Transformed(loc.Transformation())
                triangle.GetPointIds().SetId(k,points.InsertNextPoint(p.X(),p.Y(),p.Z()))
            polys.InsertNextCell(triangle)
    data=vtk.vtkPolyData(); data.SetPoints(points); data.SetPolys(polys)
    clean=vtk.vtkCleanPolyData(); clean.SetInputData(data); clean.SetTolerance(1e-9)
    normals=vtk.vtkPolyDataNormals(); normals.SetInputConnection(clean.GetOutputPort())
    normals.ConsistencyOn(); normals.AutoOrientNormalsOn(); normals.SetFeatureAngle(40)
    mapper=vtk.vtkPolyDataMapper(); mapper.SetInputConnection(normals.GetOutputPort())
    actor=vtk.vtkActor(); actor.SetMapper(mapper)
    actor.GetProperty().SetColor((.30,.62,.80) if i!=2 else (.79,.57,.25))
    actor.GetProperty().SetAmbient(.22); actor.GetProperty().SetDiffuse(.78)
    renderer=vtk.vtkRenderer(); renderer.SetViewport(i/4,0,(i+1)/4,1)
    renderer.SetBackground(244/255,246/255,248/255); renderer.AddActor(actor)
    camera=renderer.GetActiveCamera(); camera.SetPosition(17,-29,32); camera.SetFocalPoint(0,0,2)
    camera.SetViewUp(0,0,1); camera.ParallelProjectionOn(); camera.SetParallelScale(10.6)
    renderer.ResetCameraClippingRange(); window.AddRenderer(renderer)
window.Render()
capture=vtk.vtkWindowToImageFilter(); capture.SetInput(window); capture.ReadFrontBufferOff(); capture.Update()
writer=vtk.vtkPNGWriter(); writer.SetFileName("curved-render.png"); writer.SetInputConnection(capture.GetOutputPort()); writer.Write()
window.Finalize()

fig=plt.figure(figsize=(15,5.3),facecolor="#f4f6f8")
ax=fig.add_axes([0,.18,1,.66]); ax.imshow(mpimg.imread("curved-render.png")); ax.axis("off")
fig.suptitle("Custom kernel: analytic curves, blind holes and counterbores",fontsize=17,fontweight="bold",y=.97,color="#18283a")
for i,(title,body) in enumerate(parts):
    x=(i+.5)/4
    fig.text(x,.84,title,ha="center",fontsize=11,fontweight="bold",color="#18283a")
    fig.text(x,.19,f"Volume {body.volume:.3f} mm³",ha="center",fontsize=10,color="#405568")
fig.text(.5,.09,"First three panels show successive cuts on the same 16 × 10 × 4 mm block; fourth is a separate overlapping-hole example.",
         ha="center",fontsize=10,color="#405568")
fig.text(.5,.04,"Circle arcs and cylindrical walls define the models. Display tessellation and STEP export use OCCT.",ha="center",fontsize=10,color="#65798b")
fig.savefig("cylinder-experiment.png",dpi=140,facecolor=fig.get_facecolor())
print("Rendered curved boundaries with depth buffering.")
