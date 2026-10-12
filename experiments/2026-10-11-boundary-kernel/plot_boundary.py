"""Render the exact merged boundaries. OCCT tessellation is display-only."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgb
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from boundary import Body
from kernel import Solid
from compare_boundary import merged_faces
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
import math

def box(lo,hi): return Body.from_solid(Solid.box(lo,hi))
l=box((0,0,0),(2,1,1)).union(box((0,0,0),(1,2,1)))
hole=box((0,0,0),(6,4,2)).cut(box((1,1,-1),(2,3,3)))
two=hole.cut(box((4,1,-1),(5,3,3)))
fig=plt.figure(figsize=(15,5.5),facecolor="#f4f6f8")
panels=[("Before: separate pieces",l,True),("After: merged boundary",l,False),
        ("One through-hole",hole,False),("After a second cut",two,False)]
for index,(title,body,before) in enumerate(panels):
    ax=fig.add_subplot(1,4,index+1,projection="3d",facecolor="#f4f6f8")
    if before:
        for i,cell in enumerate(body.cells):
            poly=[[[float(c) for c in p] for p in f] for f in cell.faces]
            ax.add_collection3d(Poly3DCollection(poly,facecolors=["#439bd2","#e3a352","#8778c3"][i%3],
                                               edgecolors="#253e55",linewidths=1,alpha=.9))
    else:
        native_faces=merged_faces(body.boundary)
        for exact,face in zip(body.boundary.faces,native_faces):
            mesher=BRepMesh_IncrementalMesh(face,.01,False,.2,False)
            location=TopLoc_Location(); mesh=BRep_Tool.Triangulation_s(face,location)
            triangles=[]
            for i in range(1,mesh.NbTriangles()+1):
                xyz=[]
                for node in mesh.Triangle(i).Get():
                    p=mesh.Node(node).Transformed(location.Transformation()); xyz.append([p.X(),p.Y(),p.Z()])
                triangles.append(xyz)
            n=list(map(float,exact.normal)); norm=math.sqrt(sum(x*x for x in n))
            brightness=.72+.23*max(0,(n[2]-.5*n[0]-.3*n[1])/norm)
            color=tuple(c*brightness for c in to_rgb("#52a7d3" if index!=2 else "#e4ad5a"))
            ax.add_collection3d(Poly3DCollection(triangles,facecolors=color,edgecolors="none",linewidths=0,alpha=1,antialiased=False))
            for loop in exact.loops:
                closed=loop+(loop[0],); coordinates=list(zip(*closed))
                ax.plot(*[list(map(float,c)) for c in coordinates],color="#253e55",linewidth=.8)
    vertices=[p for f in body.boundary.faces for loop in f.loops for p in loop]
    lo=[min(float(p[i]) for p in vertices) for i in range(3)]
    hi=[max(float(p[i]) for p in vertices) for i in range(3)]
    size=max(b-a for a,b in zip(lo,hi)); center=[(a+b)/2 for a,b in zip(lo,hi)]
    ax.set(xlim=(center[0]-.57*size,center[0]+.57*size),
           ylim=(center[1]-.57*size,center[1]+.57*size),
           zlim=(center[2]-.45*size,center[2]+.45*size))
    ax.set_box_aspect((1,1,.8)); ax.set_axis_off(); ax.view_init(elev=35,azim=-55)
    ax.set_title(title,fontsize=12,fontweight="bold",color="#18283a",pad=0)
    label=f"{len(body.cells)} convex pieces" if before else f"{len(body.boundary.faces)} merged faces"
    ax.text2D(.5,.03,label+f" · volume {body.volume()}",transform=ax.transAxes,ha="center",fontsize=10,color="#405568")
fig.suptitle("Custom kernel: merged boundaries and repeated cuts",fontsize=18,fontweight="bold",y=.97,color="#18283a")
fig.text(.5,.075,"The same L-shaped solid before and after boundary merging; holes remain open after further cuts.",ha="center",fontsize=11,color="#405568")
fig.text(.5,.03,"Exact planar research prototype. OCCT tessellates these computed boundaries for this illustration only.",ha="center",fontsize=10,color="#65798b")
fig.subplots_adjust(left=.01,right=.99,top=.87,bottom=.15,wspace=.04)
fig.savefig("boundary-experiment.png",dpi=140,facecolor=fig.get_facecolor())
