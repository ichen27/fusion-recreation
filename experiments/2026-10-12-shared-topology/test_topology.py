from dataclasses import replace
from fractions import Fraction
import unittest
from adapters import from_planar, from_curved, contains
from topology import Boundary, Curve, Use, TopologyError
from kernel import Solid
from boundary import Body as Planar
from curves import Disk, Rect, Region
from cylinders import Body as Curved
from fixtures import workflows as planar_workflows
from curved_fixtures import workflows as curved_workflows


class TopologyTests(unittest.TestCase):
    def test_exact_cube_incidence(self):
        t = from_planar(Planar.from_solid(Solid.box((0,0,0),(1,1,1))))
        self.assertEqual((len(t.vertices),len(t.edges),len(t.faces)), (8,12,6))
        self.assertEqual(t.summary()["shell_euler"], [2])
        self.assertEqual(t.validate(), ())

    def test_exact_thin_solid_preserved(self):
        t = from_planar(Planar.from_solid(Solid.box((0,0,0),(1,1,Fraction(1,10**30)))))
        self.assertEqual(t.tolerance, 0)
        self.assertEqual(len(t.vertices), 8)
        self.assertTrue(all(isinstance(x,Fraction) for p in t.vertices for x in p))

    def test_periodic_cylinder_split_into_patches(self):
        t = from_curved(Curved.extrude(Disk(0,0,2),0,4))
        self.assertEqual((len(t.vertices),len(t.edges),len(t.faces)), (8,12,6))
        self.assertEqual(t.summary()["shell_euler"], [2])
        self.assertEqual(sum(f.surface.kind == "cylinder" for f in t.faces), 4)
        self.assertEqual(t.validate(), ())

    def test_through_hole_genus(self):
        b = Curved.extrude(Rect(-5,-5,5,5),0,4).cut(Curved.extrude(Disk(0,0,1),-1,5))
        self.assertEqual(from_curved(b).summary()["shell_euler"], [0])

    def test_two_holes_genus(self):
        b = Curved.extrude(Rect(-5,-5,5,5),0,4)
        for x in (-2,2):
            b = b.cut(Curved.extrude(Disk(x,0,1),-1,5))
        self.assertEqual(from_curved(b).summary()["shell_euler"], [-2])

    def test_blind_hole_does_not_add_handle(self):
        b = Curved.extrude(Rect(-5,-5,5,5),0,4).cut(Curved.extrude(Disk(0,0,1),2,5))
        self.assertEqual(from_curved(b).summary()["shell_euler"], [2])

    def test_cavity_has_two_shells(self):
        b = Curved.extrude(Rect(-5,-5,5,5),0,4).cut(Curved.extrude(Disk(0,0,1),1,3))
        self.assertEqual(from_curved(b).summary()["shell_euler"], [2,2])

    def test_disconnected_cylinders(self):
        b = Curved.extrude(Disk(-3,0,1),0,2).union(Curved.extrude(Disk(3,0,1),0,2))
        self.assertEqual(from_curved(b).summary()["shell_euler"], [2,2])

    def test_empty(self):
        b = Curved.extrude(Disk(0,0,1),0,2)
        self.assertEqual(from_curved(b.cut(b)).summary()["shells"], 0)

    def test_planar_corpus(self):
        for name, initial, steps in planar_workflows():
            b = Planar.from_solid(initial)
            for operation, tool in steps:
                b = getattr(b,operation)(Planar.from_solid(tool))
                with self.subTest(name=name,operation=operation):
                    self.assertEqual(from_planar(b).validate(), ())

    def test_curved_corpus(self):
        for name, initial, steps in curved_workflows():
            b = Curved.extrude(*initial)
            with self.subTest(name=name,step=0):
                self.assertEqual(from_curved(b).validate(), ())
            for step,(operation,tool) in enumerate(steps,1):
                b = getattr(b,operation)(Curved.extrude(*tool))
                with self.subTest(name=name,step=step):
                    self.assertEqual(from_curved(b).validate(), ())

    def test_removed_face_detected(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        broken = replace(t, faces=t.faces[:-1])
        self.assertIn("Open or nonmanifold edge", broken.validate())

    def test_reversed_edge_detected(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        face = t.faces[0]
        loop = face.loops[0]
        changed = replace(face, loops=((replace(loop[0],forward=not loop[0].forward),)+loop[1:],))
        broken = replace(t, faces=(changed,)+t.faces[1:])
        self.assertIn("Inconsistent edge orientation", broken.validate())

    def test_wrong_surface_detected(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        face = t.faces[0]
        changed = replace(face, surface=replace(face.surface,radius=2))
        self.assertIn("Curve off cylinder", replace(t,faces=(changed,)+t.faces[1:]).validate())

    def test_bad_vertex_and_edge_references(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        self.assertIn("Invalid vertex reference",replace(t,edges=(replace(t.edges[0],start=999),)+t.edges[1:]).validate())
        face = replace(t.faces[0],loops=((Use(999,True),),))
        self.assertIn("Invalid edge reference",replace(t,faces=(face,)+t.faces[1:]).validate())

    def test_duplicate_face_detected(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        self.assertIn("Open or nonmanifold edge",replace(t,faces=t.faces+(t.faces[0],)).validate())

    def test_nonfinite_boundary_rejected(self):
        t = from_curved(Curved.extrude(Disk(0,0,1),0,2))
        broken = replace(t, vertices=((float("nan"),0,0),)+t.vertices[1:])
        self.assertIn("Nonfinite geometry", broken.validate())
        face = replace(t.faces[0], surface=replace(t.faces[0].surface, radius=float("nan")))
        self.assertIn("Nonfinite geometry", replace(t, faces=(face,)+t.faces[1:]).validate())

    def test_point_touching_shells_rejected(self):
        from topology import Patch, build
        a = Planar.from_solid(Solid.box((0,0,0),(1,1,1)))
        b = Planar.from_solid(Solid.box((1,1,1),(2,2,2)))
        patches = []
        for body in (a,b):
            t = from_planar(body)
            for face in t.faces:
                patches.append(Patch(face.surface,tuple(tuple(t.directed(u)[2] for u in loop) for loop in face.loops)))
        with self.assertRaisesRegex(TopologyError,"Disconnected vertex"):
            build(patches)

    def test_analytic_containment(self):
        regions = [Region.of(Disk(0,0,2)), Region.of(Rect(-2,-2,2,2)),
                   Region.of(Disk(0,0,2)).union(Region.of(Disk(2,0,2)))]
        for region in regions:
            self.assertTrue(contains(region.loops[0],(.1,.2)))
            self.assertFalse(contains(region.loops[0],(8,.2)))


if __name__ == "__main__":
    unittest.main()
