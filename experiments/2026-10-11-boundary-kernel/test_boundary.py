"""Throwaway boundary-merging experiment: analytic and topological acceptance."""
import unittest
from fractions import Fraction as F
from kernel import Solid
from boundary import Body, BoundaryError

def box(lo,hi): return Body.from_solid(Solid.box(lo,hi))

class BoundaryTests(unittest.TestCase):
    def check(self,body,vol,area=None,faces=None,shells=None):
        self.assertEqual(body.boundary.volume(),vol)
        self.assertEqual(body.boundary.validate(),[])
        self.assertEqual(body.volume(),vol)
        if area is not None: self.assertAlmostEqual(body.boundary.area(),area,places=9)
        if faces is not None: self.assertEqual(len(body.boundary.faces),faces)
        if shells is not None: self.assertEqual(len(body.boundary.shells()),shells)

    def test_box(self):
        self.check(box((0,0,0),(2,3,4)),24,52,6,1)

    def test_overlapping_union_has_six_faces(self):
        a=box((0,0,0),(2,2,2)); b=box((1,0,0),(3,2,2))
        self.check(a.union(b),12,32,6,1)

    def test_face_contact_merges(self):
        a=box((0,0,0),(1,1,1)); b=box((1,0,0),(2,1,1))
        self.check(a.union(b),2,10,6,1)

    def test_l_shape_has_concave_faces(self):
        a=box((0,0,0),(2,1,1)); b=box((0,0,0),(1,2,1))
        body=a.union(b)
        self.check(body,3,14,8,1)
        self.assertEqual(sum(len(f.outer)>=6 for f in body.boundary.faces),2)

    def test_partial_face_contact_and_t_junction(self):
        a=box((0,0,0),(2,2,1)); b=box((1,0,1),(2,1,2))
        # Two side-plane pairs merge; the exposed step has nine faces.
        self.check(a.union(b),5,20,9,1)

    def test_internal_cavity(self):
        body=box((0,0,0),(4,4,4)).cut(box((1,1,1),(3,3,3)))
        self.check(body,56,120,12,2)
        self.assertEqual(sorted(body.boundary.shell_volumes()),[-8,64])

    def test_square_through_hole_and_face_loops(self):
        body=box((0,0,0),(4,4,2)).cut(box((1,1,-1),(3,3,3)))
        self.check(body,24,72,10,1)
        self.assertEqual(sum(len(f.holes) for f in body.boundary.faces),2)
        self.assertEqual(body.boundary.euler_characteristics(),[0])

    def test_disconnected_components(self):
        body=box((0,0,0),(1,1,1)).union(box((2,0,0),(3,1,1)))
        self.check(body,2,12,12,2)
        self.assertEqual(sorted(body.boundary.shell_volumes()),[1,1])

    def test_cut_splits_body(self):
        body=box((0,0,0),(3,1,1)).cut(box((1,-1,-1),(2,2,2)))
        self.check(body,2,12,12,2)

    def test_repeated_cuts_and_restore(self):
        a=box((0,0,0),(4,4,2))
        c1=box((1,1,-1),(2,2,3)); c2=box((2,1,-1),(3,2,3))
        body=a.cut(c1).cut(c2)
        self.check(body,28,72,10,1)
        self.check(body.cut(c1),28,72,10,1)
        restored=body.union(box((1,1,0),(3,2,2)))
        self.check(restored,32,64,6,1)

    def test_repeated_intersection_after_cut(self):
        body=box((0,0,0),(4,4,2)).cut(box((1,1,-1),(3,3,3)))
        result=body.intersection(box((0,0,0),(2,4,2)))
        self.check(result,12,40,10,1)

    def test_two_separate_through_holes(self):
        body=box((0,0,0),(6,4,2))
        body=body.cut(box((1,1,-1),(2,3,3))).cut(box((4,1,-1),(5,3,3)))
        self.check(body,40,104,14,1)
        self.assertEqual(sum(len(f.holes) for f in body.boundary.faces),4)
        self.assertEqual(body.boundary.euler_characteristics(),[-2])

    def test_thin_wall_exact_volume(self):
        e=F(1,10**20)
        body=box((0,0,0),(1,1,1)).cut(box((e,-1,-1),(2,2,2)))
        self.check(body,e,faces=6,shells=1)

    def test_edge_and_point_only_contact_rejected(self):
        a=box((0,0,0),(1,1,1))
        for lo,hi in [((1,1,0),(2,2,1)),((1,1,1),(2,2,2))]:
            with self.subTest(lo=lo):
                with self.assertRaises(BoundaryError): a.union(box(lo,hi))

    def test_empty(self):
        a=box((0,0,0),(1,1,1))
        self.check(a.cut(a),0,0,0,0)
        self.check(a.intersection(box((2,0,0),(3,1,1))),0,0,0,0)

    def test_rotated_boolean_and_repeated_cut(self):
        a=box((-1,-1,-1),(1,1,1))
        b=Body.from_solid(Solid.box((-1,-1,-1),(1,1,1)).affine(
            ((F(3,5),-F(4,5),0),(F(4,5),F(3,5),0),(0,0,1)),(F(1,3),F(1,7),F(1,5))))
        intersection=a.intersection(b); cut=a.cut(b); joined=a.union(b)
        for body in [intersection,cut,joined,joined.cut(b)]:
            self.assertEqual(body.boundary.validate(),[])
            self.assertEqual(body.boundary.volume(),body.volume())
        self.assertEqual(intersection.volume()+cut.volume(),8)
        self.assertEqual(joined.volume()+intersection.volume(),16)
        self.assertEqual(joined.cut(b).volume(),cut.volume())

if __name__=="__main__": unittest.main()
