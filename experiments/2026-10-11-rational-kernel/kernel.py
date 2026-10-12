"""THROWAWAY feasibility probe: exact convex polyhedra, not a production CAD kernel.

Input scalars are integers, Fraction or decimal/rational strings. Floats are
deliberately rejected. Booleans return convex cells; they do not sew a unified
boundary or preserve CAD feature references. Curved surfaces are unsupported.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from collections import Counter

def rational(x):
    if isinstance(x,bool) or not isinstance(x,(int,F,str)):
        raise ValueError("Use integer, Fraction, or exact decimal/rational string")
    try: return F(x)
    except (ValueError,ZeroDivisionError) as e: raise ValueError("Invalid scalar") from e

def point(x):
    if len(x)!=3: raise ValueError("Expected a 3D point")
    return tuple(rational(a) for a in x)

def add(a,b): return tuple(x+y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def mul(a,t): return tuple(x*t for x in a)
def dot(a,b): return sum((x*y for x,y in zip(a,b)),F(0))
def cross(a,b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def nonzero(a): return any(x!=0 for x in a)

def clean(poly):
    out=[]
    for p in poly:
        if not out or p!=out[-1]: out.append(p)
    if len(out)>1 and out[0]==out[-1]: out.pop()
    while len(out)>=3:
        redundant=next((i for i in range(len(out))
                       if not nonzero(cross(sub(out[i],out[i-1]),
                                            sub(out[(i+1)%len(out)],out[i])))),None)
        if redundant is None: break
        out.pop(redundant)
    return tuple(out) if len(out)>=3 else ()

def plane(face):
    n=cross(sub(face[1],face[0]),sub(face[2],face[0]))
    return n,dot(n,face[0])

def cap_hull(points,n):
    # Project onto a nonsingular coordinate plane and compute an exact 2D hull.
    drop=max(range(3),key=lambda i:abs(n[i]))
    axes=[i for i in range(3) if i!=drop]
    points=sorted(set(points),key=lambda p:(p[axes[0]],p[axes[1]]))
    def turn(a,b,c):
        return ((b[axes[0]]-a[axes[0]])*(c[axes[1]]-a[axes[1]])
                -(b[axes[1]]-a[axes[1]])*(c[axes[0]]-a[axes[0]]))
    lower=[]; upper=[]
    for p in points:
        while len(lower)>=2 and turn(lower[-2],lower[-1],p)<=0: lower.pop()
        lower.append(p)
    for p in reversed(points):
        while len(upper)>=2 and turn(upper[-2],upper[-1],p)<=0: upper.pop()
        upper.append(p)
    face=tuple(lower[:-1]+upper[:-1])
    if len(face)<3: return ()
    if dot(plane(face)[0],n)<0: face=tuple(reversed(face))
    return face

@dataclass(frozen=True)
class Solid:
    faces: tuple

    @staticmethod
    def extrude(polygon,height):
        h=rational(height)
        if h<=0: raise ValueError("Height must be positive")
        if any(len(p)!=2 for p in polygon): raise ValueError("Expected 2D polygon")
        pts=[tuple(rational(v) for v in p) for p in polygon]
        if len(pts)<3 or len(set(pts))!=len(pts): raise ValueError("Degenerate polygon")
        area=sum(pts[i][0]*pts[(i+1)%len(pts)][1]-pts[(i+1)%len(pts)][0]*pts[i][1]
                 for i in range(len(pts)))
        if area==0: raise ValueError("Zero area")
        if area<0: pts.reverse()
        for i,a in enumerate(pts):
            b=pts[(i+1)%len(pts)]
            for j,c in enumerate(pts):
                if j in (i,(i+1)%len(pts)): continue
                if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])<=0:
                    raise ValueError("Polygon must be simple and strictly convex")
        low=[(x,y,F(0)) for x,y in pts]; high=[(x,y,h) for x,y in pts]
        faces=[tuple(reversed(low)),tuple(high)]
        for i in range(len(pts)):
            j=(i+1)%len(pts)
            faces.append((low[i],low[j],high[j],high[i]))
        return Solid(tuple(faces))

    @staticmethod
    def box(lo,hi):
        lo,hi=point(lo),point(hi)
        if any(b<=a for a,b in zip(lo,hi)): raise ValueError("Invalid box")
        s=Solid.extrude([(lo[0],lo[1]),(hi[0],lo[1]),(hi[0],hi[1]),(lo[0],hi[1])],hi[2]-lo[2])
        return s.affine(((1,0,0),(0,1,0),(0,0,1)),(0,0,lo[2]))

    def affine(self,matrix,translation):
        if len(matrix)!=3: raise ValueError("Expected 3x3 matrix")
        m=tuple(point(row) for row in matrix); t=point(translation)
        determinant=dot(m[0],cross(m[1],m[2]))
        if determinant==0: raise ValueError("Singular transform")
        def apply(p): return add(tuple(dot(row,p) for row in m),t)
        faces=[tuple(apply(p) for p in face) for face in self.faces]
        if determinant<0: faces=[tuple(reversed(face)) for face in faces]
        return Solid(tuple(faces))

EMPTY=Solid(())

def volume(solid):
    # Oriented tetrahedra from each planar face's fan triangulation.
    return sum((dot(face[0],cross(face[i],face[i+1]))/6
                for face in solid.faces for i in range(1,len(face)-1)),F(0))

def total_volume(cells): return sum((volume(s) for s in cells),F(0))

def clip(solid,n,d):
    """Retain dot(n,p)<=d; lower-dimensional contact returns EMPTY."""
    vertices={p for face in solid.faces for p in face}
    if not vertices: return EMPTY
    distances={p:dot(n,p)-d for p in vertices}
    if max(distances.values())<=0: return solid
    if min(distances.values())>=0: return EMPTY
    faces=[]
    for face in solid.faces:
        out=[]
        for i,a in enumerate(face):
            b=face[(i+1)%len(face)]
            da,db=distances[a],distances[b]
            if da<=0: out.append(a)
            if (da<0 and db>0) or (da>0 and db<0):
                out.append(add(a,mul(sub(b,a),da/(da-db))))
        face=clean(out)
        if face: faces.append(face)
    cap=cap_hull((p for face in faces for p in face if dot(n,p)==d),n)
    if cap: faces.append(cap)
    result=Solid(tuple(faces))
    return result if volume(result)>0 else EMPTY

def intersect(a,b):
    if not a.faces or not b.faces: return EMPTY
    result=a
    for face in b.faces:
        n,d=plane(face)
        result=clip(result,n,d)
        if not result.faces: break
    return result

def subtract(a,b):
    """Disjoint-interior convex cells for A minus B; shared boundaries remain."""
    if not a.faces: return []
    if not b.faces: return [a]
    remainder=a; cells=[]
    for face in b.faces:
        n,d=plane(face)
        outside=clip(remainder,mul(n,-1),-d)
        if outside.faces: cells.append(outside)
        remainder=clip(remainder,n,d)
        if not remainder.faces: break
    return cells

def union(a,b):
    return ([a] if a.faces else [])+subtract(b,a)

def validate(solid):
    if not solid.faces: return []
    errors=[]; directed=Counter()
    vertices={p for face in solid.faces for p in face}
    for face in solid.faces:
        if len(face)<3 or len(set(face))!=len(face):
            errors.append("Degenerate face"); continue
        n,d=plane(face)
        if not nonzero(n): errors.append("Zero face normal"); continue
        if any(dot(n,p)!=d for p in face): errors.append("Nonplanar face")
        if any(dot(n,p)>d for p in vertices): errors.append("Nonconvex or inward face")
        for i,p in enumerate(face): directed[(p,face[(i+1)%len(face)])]+=1
    for (a,b),count in directed.items():
        if count!=1 or directed[(b,a)]!=1: errors.append("Open or nonmanifold edge")
    undirected={frozenset((a,b)) for a,b in directed}
    if len(vertices)-len(undirected)+len(solid.faces)!=2: errors.append("Euler mismatch")
    if volume(solid)<=0: errors.append("Nonpositive signed volume")
    return sorted(set(errors))
