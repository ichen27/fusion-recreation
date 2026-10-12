"""THROWAWAY analytic planar line/circle Boolean experiment.

Float64 model coordinates in millimeters. eps=max(1e-9,1e-12*coordinate_scale).
Near tangency and classification ambiguity raise CurveError. No polygonization
is used for modeling, area or perimeter.
"""
from dataclasses import dataclass
import math
TAU=2*math.pi

class CurveError(ValueError): pass
def add(a,b): return (a[0]+b[0],a[1]+b[1])
def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def mul(a,t): return (a[0]*t,a[1]*t)
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def norm(a): return math.hypot(*a)
def finite(values):
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values):
        raise CurveError("Finite numeric coordinates required")

@dataclass(frozen=True)
class Disk:
    x: float
    y: float
    radius: float
    def validate(self):
        finite((self.x,self.y,self.radius))
        if self.radius<=0: raise CurveError("Radius must be positive")
    def inside(self,p): return (p[0]-self.x)**2+(p[1]-self.y)**2<self.radius**2
    def supports(self): return [("circle",self.x,self.y,self.radius)]

@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    def validate(self):
        finite((self.x0,self.y0,self.x1,self.y1))
        if self.x1<=self.x0 or self.y1<=self.y0: raise CurveError("Positive rectangle extents required")
    def inside(self,p): return self.x0<p[0]<self.x1 and self.y0<p[1]<self.y1
    def supports(self):
        p=[(self.x0,self.y0),(self.x1,self.y0),(self.x1,self.y1),(self.x0,self.y1)]
        result=[]
        for i,a in enumerate(p):
            a,b=sorted((a,p[(i+1)%4])); result.append(("line",*a,*b))
        return result

def primitives(expr):
    if expr is None: return set()
    if expr[0]=="primitive": return {expr[1]}
    return primitives(expr[1])|primitives(expr[2])

def inside(expr,p):
    if expr is None: return False
    if expr[0]=="primitive": return expr[1].inside(p)
    a,b=inside(expr[1],p),inside(expr[2],p)
    return (a or b) if expr[0]=="union" else (a and b) if expr[0]=="intersection" else (a and not b)

def combine(a,b,op):
    if op=="union":
        if a is None: return b
        if b is None or a==b: return a
    elif op=="intersection":
        if a is None or b is None: return None
        if a==b: return a
    else:
        if a is None or a==b: return None
        if b is None: return a
    return (op,a,b)

@dataclass(frozen=True)
class Edge:
    kind: str
    p0: tuple
    p1: tuple
    center: tuple=()
    radius: float=0.
    start: float=0.
    sweep: float=0.
    @property
    def length(self): return norm(sub(self.p1,self.p0)) if self.kind=="line" else self.radius*abs(self.sweep)
    def point(self,t):
        if self.kind=="line": return add(self.p0,mul(sub(self.p1,self.p0),t))
        a=self.start+t*self.sweep
        return add(self.center,(self.radius*math.cos(a),self.radius*math.sin(a)))
    def tangent(self,t=.5):
        if self.kind=="line":
            v=sub(self.p1,self.p0); return mul(v,1/norm(v))
        a=self.start+t*self.sweep; direction=1 if self.sweep>0 else -1
        return (-direction*math.sin(a),direction*math.cos(a))
    def reverse(self):
        return Edge(self.kind,self.p1,self.p0,self.center,self.radius,self.start+self.sweep,-self.sweep)
    @property
    def area_integral(self):
        if self.kind=="line": return cross(self.p0,self.p1)/2
        a=self.start; b=a+self.sweep; x,y=self.center; r=self.radius
        return (r*x*(math.sin(b)-math.sin(a))+r*y*(math.cos(a)-math.cos(b))+r*r*self.sweep)/2

def support_point(s,t):
    if s[0]=="line": return add(s[1:3],mul(sub(s[3:5],s[1:3]),t))
    return (s[1]+s[3]*math.cos(t),s[2]+s[3]*math.sin(t))

def parameter(s,p):
    if s[0]=="circle": return math.atan2(p[1]-s[2],p[0]-s[1])%TAU
    v=sub(s[3:5],s[1:3]); return dot(sub(p,s[1:3]),v)/dot(v,v)

def intersections(a,b,eps):
    if a[0]=="line" and b[0]=="line":
        p=a[1:3]; q=b[1:3]; u=sub(a[3:5],p); v=sub(b[3:5],q); c=cross(u,v)
        if abs(c)<=eps*max(norm(u),norm(v)):
            if abs(cross(sub(q,p),u))>eps*norm(u): return []
            candidates=[a[1:3],a[3:5],b[1:3],b[3:5]]
            return [x for x in candidates if -eps/norm(u)<=parameter(a,x)<=1+eps/norm(u) and -eps/norm(v)<=parameter(b,x)<=1+eps/norm(v)]
        t=cross(sub(q,p),v)/c; s=cross(sub(q,p),u)/c
        return [add(p,mul(u,t))] if 0<=t<=1 and 0<=s<=1 else []
    if a[0]=="circle" and b[0]=="line": return intersections(b,a,eps)
    if a[0]=="line":
        p=a[1:3]; v=sub(a[3:5],p); center=b[1:3]; r=b[3]
        t=dot(sub(center,p),v)/dot(v,v); foot=add(p,mul(v,t))
        distance=norm(sub(foot,center))
        if abs(distance-r)<=eps:
            if -eps/norm(v)<=t<=1+eps/norm(v): raise CurveError("Line/circle tangency within numerical policy")
            return []
        if distance>r: return []
        offset=math.sqrt(max(0.,r*r-distance*distance)/dot(v,v))
        return [add(p,mul(v,u)) for u in (t-offset,t+offset) if 0<=u<=1]
    p=a[1:3]; q=b[1:3]; r=a[3]; s=b[3]; d=norm(sub(q,p))
    if d<=eps:
        if abs(r-s)<=eps: raise CurveError("Near-coincident circles require explicit resolution")
        return []
    if abs(d-r-s)<=eps or abs(d-abs(r-s))<=eps:
        raise CurveError("Circle/circle tangency within numerical policy")
    if d>r+s or d<abs(r-s): return []
    along=(r*r-s*s+d*d)/(2*d); height=math.sqrt(max(0.,r*r-along*along))
    u=mul(sub(q,p),1/d); foot=add(p,mul(u,along)); v=(-u[1],u[0])
    return [add(foot,mul(v,height)),add(foot,mul(v,-height))]

def simplify_loop(loop,eps):
    loop=list(loop)
    changed=True
    while changed and len(loop)>1:
        changed=False
        for i,a in enumerate(loop):
            j=(i+1)%len(loop); b=loop[j]; merged=None
            if a.kind==b.kind=="arc" and a.center==b.center and a.radius==b.radius and a.sweep*b.sweep>0:
                merged=Edge("arc",a.p0,b.p1,a.center,a.radius,a.start,a.sweep+b.sweep)
            elif a.kind==b.kind=="line":
                u=sub(a.p1,a.p0); v=sub(b.p1,b.p0)
                if abs(cross(u,v))<=eps*max(norm(u),norm(v)) and dot(u,v)>0:
                    merged=Edge("line",a.p0,b.p1)
            if merged is not None:
                if j==0: loop=[merged]+loop[1:i]
                else: loop=loop[:i]+[merged]+loop[j+1:]
                changed=True; break
    return tuple(loop)

@dataclass(frozen=True)
class Region:
    expr: object
    loops: tuple
    eps: float

    @staticmethod
    def of(primitive):
        primitive.validate()
        return Region.build(("primitive",primitive))

    @staticmethod
    def build(expr):
        items=primitives(expr)
        supports=sorted(set(s for p in items for s in p.supports()))
        scale=max([1.]+[abs(v) for s in supports for v in s[1:]])
        eps=max(1e-9,1e-12*scale)
        for p in items:
            size=p.radius if isinstance(p,Disk) else min(p.x1-p.x0,p.y1-p.y0)
            if size<=128*eps: raise CurveError("Feature below supported numerical resolution")
        params=[[0.,TAU] if s[0]=="circle" else [0.,1.] for s in supports]
        for i,a in enumerate(supports):
            for j in range(i):
                for point in intersections(a,supports[j],eps):
                    params[i].append(parameter(a,point)); params[j].append(parameter(supports[j],point))
        candidates=[]
        for s,values in zip(supports,params):
            maxparam=TAU if s[0]=="circle" else 1.
            extent=s[3] if s[0]=="circle" else norm(sub(s[3:5],s[1:3]))
            values=sorted(min(maxparam,max(0.,t)) for t in values); unique=[]
            for t in values:
                if not unique or t-unique[-1]>eps/extent: unique.append(t)
            if maxparam-unique[-1]<=eps/extent: unique[-1]=maxparam
            for t0,t1 in zip(unique,unique[1:]):
                edge=Edge("line",support_point(s,t0),support_point(s,t1)) if s[0]=="line" else Edge("arc",support_point(s,t0),support_point(s,t1),s[1:3],s[3],t0,t1-t0)
                if edge.length<=64*eps: raise CurveError("Boundary interval below supported resolution")
                midpoint=edge.point(.5); tangent=edge.tangent(); left=(-tangent[1],tangent[0])
                probes=[(inside(expr,add(midpoint,mul(left,k*eps))),
                         inside(expr,add(midpoint,mul(left,-k*eps)))) for k in (8,16,32)]
                if len(set(probes))!=1: raise CurveError("Ambiguous side classification")
                l,r=probes[0]
                if l!=r: candidates.append(edge if l else edge.reverse())
        vertices=[]; records=[]; seen=set()
        def node(p):
            matches=[i for i,q in enumerate(vertices) if norm(sub(p,q))<=4*eps]
            if len(matches)>1: raise CurveError("Ambiguous vertex clustering")
            if matches: return matches[0]
            vertices.append(p); return len(vertices)-1
        for edge in candidates:
            a,b=node(edge.p0),node(edge.p1)
            key=(edge.kind,a,b,edge.center,edge.radius,round(edge.sweep,12) if edge.kind=="arc" else 0)
            if key not in seen: records.append((a,b,edge)); seen.add(key)
        outgoing={}; incoming={}
        for i,(a,b,edge) in enumerate(records):
            if a in outgoing or b in incoming: raise CurveError("Nonmanifold or ambiguous planar boundary")
            outgoing[a]=i; incoming[b]=i
        if set(outgoing)!=set(incoming): raise CurveError("Open planar boundary")
        loops=[]; unused=set(range(len(records)))
        while unused:
            index=min(unused); start=records[index][0]; loop=[]
            while True:
                if index not in unused: raise CurveError("Broken planar loop")
                unused.remove(index); a,b,edge=records[index]; loop.append(edge)
                if b==start: break
                index=outgoing[b]
            loops.append(simplify_loop(loop,eps))
        result=Region(expr,tuple(loops),eps)
        if result.area<-eps*eps: raise CurveError("Negative region area")
        return result

    @property
    def edges(self): return tuple(e for loop in self.loops for e in loop)
    @property
    def area(self): return sum(e.area_integral for e in self.edges)
    @property
    def perimeter(self): return sum(e.length for e in self.edges)
    def union(self,other): return Region.build(combine(self.expr,other.expr,"union"))
    def cut(self,other): return Region.build(combine(self.expr,other.expr,"cut"))
    def intersection(self,other): return Region.build(combine(self.expr,other.expr,"intersection"))
