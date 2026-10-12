"""THROWAWAY 2.5D analytic solids: parallel-axis extrusions and repeated Booleans."""
from dataclasses import dataclass
import math
from curves import Region,CurveError,finite,combine,norm,sub

@dataclass(frozen=True)
class Slab:
    z0: float
    z1: float
    region: Region

@dataclass(frozen=True)
class Wall:
    edge: object
    z0: float
    z1: float

@dataclass(frozen=True)
class Cap:
    z: float
    normal: int
    region: Region

@dataclass(frozen=True)
class Body:
    slabs: tuple
    walls: tuple
    caps: tuple

    @staticmethod
    def extrude(profile,z0,z1):
        finite((z0,z1))
        eps=max(1e-9,1e-12*max(1,abs(z0),abs(z1)))
        if z1-z0<=128*eps: raise CurveError("Positive, resolvable extrusion height required")
        return Body.make((Slab(z0,z1,Region.of(profile)),))

    @staticmethod
    def make(slabs):
        slabs=tuple(s for s in slabs if s.region.loops)
        walls=tuple(Wall(e,s.z0,s.z1) for s in slabs for e in s.region.edges)
        levels=sorted(set(z for s in slabs for z in (s.z0,s.z1)))
        caps=[]; empty=Region.build(None)
        for z in levels:
            below=next((s.region for s in slabs if s.z1==z),empty)
            above=next((s.region for s in slabs if s.z0==z),empty)
            for normal,region in ((1,below.cut(above)),(-1,above.cut(below))):
                if region.loops: caps.append(Cap(z,normal,region))
        body=Body(slabs,walls,tuple(caps))
        errors=body.validate()
        if errors: raise CurveError("; ".join(errors))
        return body

    def apply(self,other,operation):
        levels=sorted(set(z for s in self.slabs+other.slabs for z in (s.z0,s.z1)))
        slabs=[]
        for lo,hi in zip(levels,levels[1:]):
            eps=max(1e-9,1e-12*max(1,abs(lo),abs(hi)))
            if hi-lo<=128*eps: raise CurveError("Depth intervals below numerical resolution")
            mid=(lo+hi)/2
            a=next((s.region.expr for s in self.slabs if s.z0<mid<s.z1),None)
            b=next((s.region.expr for s in other.slabs if s.z0<mid<s.z1),None)
            region=Region.build(combine(a,b,operation))
            if region.loops: slabs.append(Slab(lo,hi,region))
        # Merge adjacent identical expression regions without inferring equality from area.
        compact=[]
        for s in slabs:
            if compact and compact[-1].z1==s.z0 and compact[-1].region.expr==s.region.expr:
                last=compact[-1]; compact[-1]=Slab(last.z0,s.z1,s.region)
            else: compact.append(s)
        return Body.make(compact)

    def cut(self,other): return self.apply(other,"cut")
    def union(self,other): return self.apply(other,"union")
    def intersection(self,other): return self.apply(other,"intersection")
    @property
    def volume(self): return sum(s.region.area*(s.z1-s.z0) for s in self.slabs)
    @property
    def area(self): return sum(w.edge.length*(w.z1-w.z0) for w in self.walls)+sum(c.region.area for c in self.caps)
    @property
    def boundary_volume(self):
        return (sum(2*w.edge.area_integral*(w.z1-w.z0) for w in self.walls)
                +sum(c.normal*c.z*c.region.area for c in self.caps))/3

    def validate(self):
        errors=[]
        if not all(math.isfinite(x) for x in (self.volume,self.area,self.boundary_volume)):
            errors.append("Nonfinite measurement")
        if self.volume<0 or self.area<0: errors.append("Negative measurement")
        if abs(self.volume-self.boundary_volume)>max(1e-7,abs(self.volume)*1e-10):
            errors.append("Boundary and slab volume mismatch")
        for region in [s.region for s in self.slabs]+[c.region for c in self.caps]:
            if region.loops and region.area<=region.eps**2: errors.append("Unresolved region area")
            for loop in region.loops:
                for i,e in enumerate(loop):
                    if norm(sub(e.p1,loop[(i+1)%len(loop)].p0))>8*region.eps: errors.append("Open curve loop")
                    if e.length<=0: errors.append("Degenerate edge")
        return sorted(set(errors))
