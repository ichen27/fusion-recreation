"""THROWAWAY exact planar boundary extraction from disjoint convex cells.

The Body retains its convex cells for repeated Boolean operations. Boundary
faces merge coplanar fragments and can have concave outer loops and holes.
No curves, stable CAD IDs, boundary-only Boolean engine or general input parser.
"""
from dataclasses import dataclass
from collections import defaultdict, Counter
from fractions import Fraction as F
from math import sqrt
from kernel import (Solid, add, sub, mul, dot, cross, nonzero, plane, clean,
                    intersect, subtract, total_volume, validate as cell_validate)

class BoundaryError(ValueError): pass

def canonical_plane(poly):
    n,d=plane(poly)
    pivot=next(x for x in n if x)
    return tuple(x/pivot for x in n)+(d/pivot,), 1 if pivot>0 else -1

def polygon_clip(poly,n,d):
    out=[]
    for i,a in enumerate(poly):
        b=poly[(i+1)%len(poly)]; da=dot(n,a)-d; db=dot(n,b)-d
        if da<=0: out.append(a)
        if (da<0<db) or (db<0<da): out.append(add(a,mul(sub(b,a),da/(da-db))))
    return clean(out)

def polygon_subtract(subject,cutter):
    """Convex coplanar subject minus cutter, preserving subject orientation."""
    n,_=plane(cutter); remainder=subject; pieces=[]
    for i,a in enumerate(cutter):
        b=cutter[(i+1)%len(cutter)]
        edge_normal=cross(sub(b,a),n); d=dot(edge_normal,a)
        outside=polygon_clip(remainder,mul(edge_normal,-1),-d)
        if outside: pieces.append(outside)
        remainder=polygon_clip(remainder,edge_normal,d)
        if not remainder: break
    return pieces

def loop_vector(loop):
    result=(F(0),F(0),F(0))
    for i,p in enumerate(loop): result=add(result,cross(p,loop[(i+1)%len(loop)]))
    return result

def split_edge(a,b,vertices):
    v=sub(b,a); axis=next(i for i,x in enumerate(v) if x)
    points={F(0):a,F(1):b}
    for p in vertices:
        u=sub(p,a)
        if nonzero(cross(u,v)): continue
        t=u[axis]/v[axis]
        if 0<t<1: points[t]=p
    return [p for _,p in sorted(points.items())]

def inside_loop(p,loop,normal):
    """Exact even/odd point inclusion for a coplanar loop; boundary is explicit."""
    drop=max(range(3),key=lambda i:abs(normal[i])); x,y=[i for i in range(3) if i!=drop]
    inside=False
    for i,a in enumerate(loop):
        b=loop[(i+1)%len(loop)]
        v=sub(b,a); u=sub(p,a)
        if not nonzero(cross(v,u)) and all(min(a[k],b[k])<=p[k]<=max(a[k],b[k]) for k in range(3)):
            raise BoundaryError("Touching planar loops require unsupported topology")
        if (a[y]>p[y]) != (b[y]>p[y]):
            crossing=a[x]+(p[y]-a[y])*(b[x]-a[x])/(b[y]-a[y])
            if p[x]<crossing: inside=not inside
    return inside

@dataclass(frozen=True)
class Face:
    normal: tuple
    offset: F
    outer: tuple
    holes: tuple=()

    @property
    def loops(self): return (self.outer,)+self.holes

def loops_from_edges(edges):
    outgoing=defaultdict(list); incoming=Counter()
    for a,b in sorted(edges):
        outgoing[a].append(b); incoming[b]+=1
    if any(len(v)!=1 or incoming[k]!=1 for k,v in outgoing.items()):
        raise BoundaryError("Nonmanifold or touching planar patch boundary")
    remaining=set(edges); loops=[]
    while remaining:
        start,_=min(remaining); loop=[]; p=start
        while True:
            loop.append(p); nxt=outgoing[p][0]
            if (p,nxt) not in remaining: raise BoundaryError("Broken boundary loop")
            remaining.remove((p,nxt)); p=nxt
            if p==start: break
        if len(loop)<3: raise BoundaryError("Degenerate boundary loop")
        loops.append(tuple(loop))
    return loops

def build_boundary(cells):
    # Precondition: valid cells with disjoint interiors, guaranteed by Body operations.
    groups=defaultdict(lambda:{1:[],-1:[]})
    for cell in cells:
        for face in cell.faces:
            key,sign=canonical_plane(face); groups[key][sign].append(face)
    patches={}
    for key,sides in sorted(groups.items()):
        for sign in (1,-1):
            exposed=[]
            for poly in sides[sign]:
                pieces=[poly]
                for cutter in sides[-sign]:
                    pieces=[p for part in pieces for p in polygon_subtract(part,cutter)]
                    if not pieces: break
                exposed.extend(pieces)
            if exposed: patches[(key,sign)]=exposed
    vertices={p for polys in patches.values() for poly in polys for p in poly}
    faces=[]
    for (key,sign),polys in sorted(patches.items()):
        directed=Counter()
        for poly in polys:
            for i,a in enumerate(poly):
                points=split_edge(a,poly[(i+1)%len(poly)],vertices)
                for left,right in zip(points,points[1:]): directed[(left,right)]+=1
        edges=set()
        for (a,b),count in directed.items():
            net=count-directed[(b,a)]
            if net>1: raise BoundaryError("Overlapping planar patches")
            if net==1: edges.add((a,b))
        if not edges: continue
        n=mul(key[:3],sign); d=key[3]*sign
        loops=loops_from_edges(edges)
        outers=[loop for loop in loops if dot(loop_vector(loop),n)>0]
        holes=[loop for loop in loops if dot(loop_vector(loop),n)<0]
        if len(outers)+len(holes)!=len(loops): raise BoundaryError("Zero area loop")
        assigned={outer:[] for outer in outers}
        for hole in holes:
            containers=[outer for outer in outers if inside_loop(hole[0],outer,n)]
            if not containers: raise BoundaryError("Hole without enclosing face")
            outer=min(containers,key=lambda loop:dot(loop_vector(loop),n))
            assigned[outer].append(hole)
        faces.extend(Face(n,d,outer,tuple(assigned[outer])) for outer in outers)
    # Remove a collinear vertex only if every incident face agrees. This keeps
    # shared edges segmented consistently and preserves actual T-junction corners.
    straight=defaultdict(list)
    for face in faces:
        for loop in face.loops:
            for i,p in enumerate(loop):
                straight[p].append(not nonzero(cross(sub(p,loop[i-1]),sub(loop[(i+1)%len(loop)],p))))
    removable={p for p,flags in straight.items() if all(flags)}
    faces=[Face(f.normal,f.offset,tuple(p for p in f.outer if p not in removable),
                tuple(tuple(p for p in loop if p not in removable) for loop in f.holes)) for f in faces]
    result=Boundary(tuple(faces))
    errors=result.validate()
    if errors: raise BoundaryError("; ".join(errors))
    if result.volume()!=total_volume(cells): raise BoundaryError("Boundary/cell volume mismatch")
    return result

@dataclass(frozen=True)
class Boundary:
    faces: tuple

    def volume(self):
        return sum((dot(loop[0],cross(loop[i],loop[i+1]))/6
                    for f in self.faces for loop in f.loops
                    for i in range(1,len(loop)-1)),F(0))

    def area(self):
        return sum(float(dot(loop_vector(loop),f.normal))/(2*sqrt(float(dot(f.normal,f.normal))))
                   for f in self.faces for loop in f.loops)

    def edge_owners(self):
        owners=defaultdict(list)
        for index,f in enumerate(self.faces):
            for loop in f.loops:
                for i,a in enumerate(loop):
                    b=loop[(i+1)%len(loop)]
                    owners[tuple(sorted((a,b)))].append((index,a,b))
        return owners

    def shells(self):
        neighbors=defaultdict(set)
        for entries in self.edge_owners().values():
            ids={i for i,_,_ in entries}
            for i in ids: neighbors[i].update(ids-{i})
        unseen=set(range(len(self.faces))); shells=[]
        while unseen:
            stack=[min(unseen)]; found=set()
            while stack:
                i=stack.pop()
                if i in found: continue
                found.add(i); stack.extend(neighbors[i]-found)
            unseen-=found; shells.append(tuple(sorted(found)))
        return shells

    def shell_volumes(self):
        return [Boundary(tuple(self.faces[i] for i in shell)).volume() for shell in self.shells()]

    def euler_characteristics(self):
        result=[]
        for shell in self.shells():
            faces=[self.faces[i] for i in shell]
            vertices={p for f in faces for loop in f.loops for p in loop}
            edges={tuple(sorted((p,loop[(i+1)%len(loop)])))
                   for f in faces for loop in f.loops for i,p in enumerate(loop)}
            result.append(len(vertices)-len(edges)+sum(1-len(f.holes) for f in faces))
        return result

    def validate(self):
        errors=[]; owners=self.edge_owners()
        for f in self.faces:
            if not nonzero(f.normal): errors.append("Zero normal")
            for j,loop in enumerate(f.loops):
                if len(loop)<3 or len(set(loop))!=len(loop): errors.append("Degenerate loop")
                if any(dot(f.normal,p)!=f.offset for p in loop): errors.append("Nonplanar loop")
                orientation=dot(loop_vector(loop),f.normal)
                if (j==0 and orientation<=0) or (j>0 and orientation>=0):
                    errors.append("Incorrect loop orientation")
        for entries in owners.values():
            if len(entries)!=2 or entries[0][1:]!=tuple(reversed(entries[1][1:])):
                errors.append("Open or nonmanifold edge")
        # Each manifold vertex has one connected cyclic link of incident faces.
        vertex_links=defaultdict(lambda:defaultdict(list))
        for (a,b),entries in owners.items():
            if len(entries)!=2: continue
            i,j=entries[0][0],entries[1][0]
            for p in (a,b):
                vertex_links[p][i].append(j); vertex_links[p][j].append(i)
        for graph in vertex_links.values():
            if any(len(adj)!=2 for adj in graph.values()): errors.append("Nonmanifold vertex")
            found=set(); stack=[next(iter(graph))]
            while stack:
                p=stack.pop()
                if p in found: continue
                found.add(p); stack.extend(graph[p])
            if len(found)!=len(graph): errors.append("Disconnected vertex link")
        for euler in self.euler_characteristics():
            if euler>2 or euler%2: errors.append("Invalid orientable shell topology")
        if self.faces and self.volume()<=0: errors.append("Nonpositive total volume")
        return sorted(set(errors))

@dataclass(frozen=True)
class Body:
    cells: tuple
    boundary: Boundary

    @staticmethod
    def _make(cells):
        cells=tuple(c for c in cells if c.faces)
        return Body(cells,build_boundary(cells))

    @staticmethod
    def from_solid(solid):
        errors=cell_validate(solid)
        if errors: raise BoundaryError("; ".join(errors))
        return Body._make((solid,))

    def volume(self): return total_volume(self.cells)

    def cut(self,other):
        cells=list(self.cells)
        for cutter in other.cells: cells=[piece for c in cells for piece in subtract(c,cutter)]
        return Body._make(cells)

    def intersection(self,other):
        return Body._make(intersect(a,b) for a in self.cells for b in other.cells)

    def union(self,other):
        additional=list(other.cells)
        for existing in self.cells:
            additional=[piece for c in additional for piece in subtract(c,existing)]
        return Body._make(self.cells+tuple(additional))
