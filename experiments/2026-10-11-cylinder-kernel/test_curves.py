"""Acceptance for the disposable parallel-axis analytic-curve experiment."""
import math,unittest
from curves import Disk,Rect,Region,CurveError
from cylinders import Body

class CurvesTest(unittest.TestCase):
    def test_disk_analytic(self):
        r=Region.of(Disk(0,0,3))
        self.assertAlmostEqual(r.area,9*math.pi,places=10)
        self.assertAlmostEqual(r.perimeter,6*math.pi,places=10)
        self.assertEqual(len(r.loops),1)
        self.assertTrue(all(e.kind=="arc" for e in r.edges))

    def test_rectangle(self):
        r=Region.of(Rect(0,0,40,20))
        self.assertAlmostEqual(r.area,800)
        self.assertAlmostEqual(r.perimeter,120)

    def test_circular_hole(self):
        r=Region.of(Rect(-10,-10,10,10)).cut(Region.of(Disk(0,0,3)))
        self.assertAlmostEqual(r.area,400-9*math.pi,places=9)
        self.assertEqual(len(r.loops),2)

    def test_overlap_disks_lens(self):
        a=Region.of(Disk(0,0,1)); b=Region.of(Disk(1,0,1))
        lens=2*math.pi/3-math.sqrt(3)/2
        self.assertAlmostEqual(a.intersection(b).area,lens,places=10)
        self.assertAlmostEqual(a.union(b).area,2*math.pi-lens,places=10)
        self.assertAlmostEqual(a.cut(b).area,math.pi-lens,places=10)

    def test_line_circle_half_disk(self):
        r=Region.of(Disk(0,0,2)).intersection(Region.of(Rect(0,-3,3,3)))
        self.assertAlmostEqual(r.area,2*math.pi,places=10)
        self.assertAlmostEqual(r.perimeter,2*math.pi+4,places=10)
        self.assertEqual({e.kind for e in r.edges},{"line","arc"})

    def test_concentric_ring(self):
        r=Region.of(Disk(0,0,3)).cut(Region.of(Disk(0,0,1)))
        self.assertAlmostEqual(r.area,8*math.pi,places=10)
        self.assertAlmostEqual(r.perimeter,8*math.pi,places=10)
        self.assertEqual(len(r.loops),2)

    def test_idempotence_and_empty(self):
        a=Region.of(Disk(0,0,2))
        self.assertAlmostEqual(a.union(a).area,a.area)
        self.assertEqual(a.cut(a).area,0)
        r=Region.of(Rect(-5,-5,5,5)).cut(a)
        self.assertAlmostEqual(r.cut(a).area,r.area)

    def test_partial_collinear_rectangle_union(self):
        a=Region.of(Rect(0,0,2,1)); b=Region.of(Rect(1,0,3,1))
        self.assertAlmostEqual(a.union(b).area,3)
        self.assertAlmostEqual(a.union(b).perimeter,8)

    def test_tangency_and_near_tangency_rejected(self):
        a=Region.of(Disk(0,0,1))
        for x in (2,2+1e-10,2-1e-10):
            with self.subTest(x=x):
                with self.assertRaises(CurveError): a.union(Region.of(Disk(x,0,1)))

    def test_invalid_dimensions(self):
        for args in [(0,0,0),(0,0,-1),(math.nan,0,1),(0,math.inf,1)]:
            with self.assertRaises(CurveError): Region.of(Disk(*args))
        with self.assertRaises(CurveError): Region.of(Rect(1,0,0,1))

class CylinderTest(unittest.TestCase):
    def check(self,b,volume,area=None):
        self.assertAlmostEqual(b.volume,volume,places=8)
        self.assertEqual(b.validate(),[])
        if area is not None: self.assertAlmostEqual(b.area,area,places=8)

    def test_cylinder(self):
        self.check(Body.extrude(Disk(0,0,3),0,10),90*math.pi,78*math.pi)

    def test_through_hole(self):
        b=Body.extrude(Rect(0,0,40,20),0,10)
        r=b.cut(Body.extrude(Disk(20,10,3),-1,11))
        self.check(r,8000-90*math.pi,2800+42*math.pi)
        self.assertTrue(any(w.edge.kind=="arc" for w in r.walls))

    def test_blind_hole(self):
        b=Body.extrude(Rect(-10,-10,10,10),0,10)
        self.check(b.cut(Body.extrude(Disk(0,0,3),6,11)),4000-36*math.pi,1600+24*math.pi)

    def test_counterbore(self):
        b=Body.extrude(Rect(-10,-10,10,10),0,10)
        b=b.cut(Body.extrude(Disk(0,0,2),-1,11)).cut(Body.extrude(Disk(0,0,4),7,11))
        self.check(b,4000-76*math.pi,1600+44*math.pi)

    def test_overlapping_through_holes(self):
        b=Body.extrude(Rect(-4,-4,4,4),0,3)
        a=Body.extrude(Disk(0,0,1),-1,4); c=Body.extrude(Disk(1,0,1),-1,4)
        lens=2*math.pi/3-math.sqrt(3)/2
        self.check(b.cut(a).cut(c),192-3*(2*math.pi-lens))

    def test_partial_depth_overlapping_holes(self):
        b=Body.extrude(Rect(-4,-4,4,4),0,10)
        a=Body.extrude(Disk(0,0,1),2,11); c=Body.extrude(Disk(1,0,1),6,11)
        lens=2*math.pi/3-math.sqrt(3)/2
        self.check(b.cut(a).cut(c),640-8*math.pi-4*(math.pi-lens))

    def test_disk_union_intersection_different_heights(self):
        a=Body.extrude(Disk(0,0,1),0,3); b=Body.extrude(Disk(1,0,1),1,4)
        lens=2*math.pi/3-math.sqrt(3)/2
        self.check(a.intersection(b),2*lens)
        self.check(a.union(b),6*math.pi-2*lens)

    def test_external_breakout(self):
        b=Body.extrude(Rect(0,-3,4,3),0,2)
        self.check(b.cut(Body.extrude(Disk(0,0,2),-1,3)),48-4*math.pi)

    def test_disconnected_cylinders(self):
        a=Body.extrude(Disk(-3,0,1),0,2); b=Body.extrude(Disk(3,0,1),0,2)
        self.check(a.union(b),4*math.pi,12*math.pi)

    def test_empty_repeated_cut(self):
        a=Body.extrude(Disk(0,0,1),0,2)
        self.check(a.cut(a),0,0)
        b=Body.extrude(Rect(-4,-4,4,4),0,2).cut(a)
        self.check(b.cut(a),b.volume,b.area)

    def test_numerical_policy_does_not_change_input(self):
        b=Body.extrude(Rect(-4,-4,4,4),0,2)
        with self.assertRaises(CurveError): b.cut(Body.extrude(Disk(3,0,1),0,2))
        self.check(b,128,192)

if __name__=="__main__": unittest.main()
