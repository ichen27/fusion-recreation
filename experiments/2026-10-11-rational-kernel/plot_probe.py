from fractions import Fraction as F
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from kernel import Solid,intersect,subtract,union,total_volume
a=Solid.box((-1,-1,-1),(1,1,1))
b=a.affine(((F(3,5),-F(4,5),0),(F(4,5),F(3,5),0),(0,0,1)),(F(3,5),F(1,5),F(2,5)))
fig=plt.figure(figsize=(15,5.2),facecolor="#f4f6f8")
palette=["#2879ba","#ef9c47","#7b65bc","#38a693","#cf6382","#608aae","#ac9356"]
panels=[("Input solids",[a,b]),("Intersection",[intersect(a,b)]),
        ("Subtract B from A",subtract(a,b)),("Union as convex pieces",union(a,b))]
for i,(title,cells) in enumerate(panels):
    ax=fig.add_subplot(1,4,i+1,projection="3d",facecolor="#f4f6f8")
    for k,s in enumerate(cells):
        polys=[[[float(c) for c in p] for p in face] for face in s.faces]
        ax.add_collection3d(Poly3DCollection(polys,facecolors=palette[k%len(palette)],
                            edgecolors="#24394f",linewidths=.6,alpha=.32 if i==0 else .72))
    ax.set(xlim=(-1.6,2.2),ylim=(-1.6,2.2),zlim=(-1.5,2.1))
    ax.set_box_aspect((1,1,1)); ax.view_init(elev=23,azim=-58); ax.set_axis_off()
    ax.set_title(title,fontsize=12,fontweight="bold",pad=0,color="#18283a")
    label="Two overlapping boxes" if i==0 else f"{len(cells)} cell(s) · volume {float(total_volume(cells)):.6f}"
    ax.text2D(.5,.02,label,transform=ax.transAxes,ha="center",fontsize=10,color="#405568")
fig.suptitle("Custom kernel experiment: exact solids with flat faces",fontsize=18,fontweight="bold",x=.5,y=.97,color="#18283a")
fig.text(.5,.075,"Computed by the experimental kernel. Colors distinguish pieces; internal boundaries are not merged.",ha="center",fontsize=11,color="#405568")
fig.text(.5,.025,"Throwaway feasibility probe · curved surfaces, fillets, editable history and production robustness are not implemented.",ha="center",fontsize=10,color="#65798b")
fig.subplots_adjust(left=.015,right=.985,top=.87,bottom=.15,wspace=.02)
fig.savefig("kernel-experiment.png",dpi=140,facecolor=fig.get_facecolor())
