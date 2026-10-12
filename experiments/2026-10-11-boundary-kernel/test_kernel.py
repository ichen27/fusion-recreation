"""Disposable kernel experiment. Run on the mini with python3 -m unittest -v."""
import random
import unittest
from fractions import Fraction as F
from kernel import Solid, intersect, subtract, union, validate, volume, total_volume

class KernelTest(unittest.TestCase):
    def test_extrusion_analytic_volume(self):
        s=Solid.extrude([(0,0),(40,0),(40,20),(0,20)],10)
        self.assertEqual(volume(s),8000)
        self.assertEqual(validate(s),[])
        self.assertEqual(volume(Solid.extrude([(0,0),(4,0),(0,3)],5)),30)

    def test_winding_normalized(self):
        a=[(0,0),(40,0),(40,20),(0,20)]
        self.assertEqual(volume(Solid.extrude(list(reversed(a)),10)),8000)

    def test_analytic_overlap(self):
        a=Solid.box((0,0,0),(4,4,4)); b=Solid.box((2,1,1),(6,3,3))
        c=intersect(a,b)
        self.assertEqual(volume(c),8)
        self.assertEqual(total_volume(subtract(a,b)),56)
        self.assertEqual(total_volume(union(a,b)),72)
        for s in [c,*subtract(a,b),*union(a,b)]: self.assertEqual(validate(s),[])

    def test_exact_near_contact(self):
        e=F(1,10**30); a=Solid.box((0,0,0),(1,1,1))
        b=Solid.box((1-e,0,0),(2,1,1))
        self.assertEqual(volume(intersect(a,b)),e)
        self.assertEqual(total_volume(subtract(a,b)),1-e)
        self.assertEqual(validate(intersect(a,b)),[])

    def test_touching_and_disjoint(self):
        a=Solid.box((0,0,0),(1,1,1))
        for lo,hi in [((1,0,0),(2,1,1)),((1,1,0),(2,2,1)),
                      ((1,1,1),(2,2,2)),((2,0,0),(3,1,1))]:
            b=Solid.box(lo,hi)
            self.assertEqual(volume(intersect(a,b)),0)
            self.assertEqual(total_volume(subtract(a,b)),1)
            self.assertEqual(total_volume(union(a,b)),2)

    def test_identical_and_containment(self):
        a=Solid.box((0,0,0),(4,4,4)); b=Solid.box((1,1,1),(3,3,3))
        self.assertEqual(volume(intersect(a,a)),64)
        self.assertEqual(subtract(a,a),[])
        self.assertEqual(total_volume(union(a,a)),64)
        self.assertEqual(volume(intersect(a,b)),8)
        self.assertEqual(total_volume(subtract(a,b)),56)
        self.assertEqual(total_volume(union(a,b)),64)

    def test_rotated_diamond(self):
        # Diamond prism area 2; clipped by unit square area 1/2, height 2.
        a=Solid.extrude([(0,-1),(1,0),(0,1),(-1,0)],2)
        b=Solid.box((0,0,0),(1,1,2))
        self.assertEqual(volume(intersect(a,b)),1)
        self.assertEqual(total_volume(union(a,b)),5)

    def test_general_rational_rotation(self):
        # Orthogonal determinant-one rotation: cos=3/5, sin=4/5.
        a=Solid.box((-1,-1,-1),(1,1,1))
        m=((F(3,5),-F(4,5),0),(F(4,5),F(3,5),0),(0,0,1))
        b=a.affine(m,(0,0,0)); c=intersect(a,b)
        # Each of four clipped corners is a 1/2 * (2/3) * (1/2) triangle.
        self.assertEqual(volume(c),F(20,3))
        self.assertEqual(validate(c),[])
        self.assertEqual(volume(b),8)

    def test_affine_reflection_and_translation(self):
        a=Solid.box((0,0,0),(2,3,4))
        b=a.affine(((-1,0,0),(0,2,0),(0,0,1)),(10**12,-10**12,7))
        self.assertEqual(volume(b),48)
        self.assertEqual(validate(b),[])

    def test_invalid_inputs(self):
        for polygon,height in [
            ([(0,0),(1,0)],1),
            ([(0,0),(1,0),(0,1)],0),
            ([(0,0),(1,0),(0,1)],-1),
            ([(0,0),(1,1),(0,1),(1,0)],1),
            ([(0,0),(2,0),(1,1),(2,2),(0,2)],1),
            ([(0,0),(1,0),(1,0),(0,1)],1),
            ([(0,0),(float('nan'),0),(0,1)],1),
            ([(0,0),(float('inf'),0),(0,1)],1),
            ([(0,0),(0.1,0),(0,1)],1)]:
            with self.subTest(polygon=polygon,height=height):
                with self.assertRaises(ValueError): Solid.extrude(polygon,height)
        with self.assertRaises(ValueError): Solid.box((1,0,0),(0,1,1))
        with self.assertRaises(ValueError):
            Solid.box((0,0,0),(1,1,1)).affine(((0,0,0),(0,1,0),(0,0,1)),(0,0,0))

    def test_seeded_box_corpus(self):
        rng=random.Random(42017)
        for i in range(120):
            al=tuple(F(rng.randrange(-20,20),7) for _ in range(3))
            bl=tuple(F(rng.randrange(-20,20),7) for _ in range(3))
            ah=tuple(x+F(rng.randrange(1,30),7) for x in al)
            bh=tuple(x+F(rng.randrange(1,30),7) for x in bl)
            a,b=Solid.box(al,ah),Solid.box(bl,bh)
            expected=F(1)
            for j in range(3): expected*=max(F(0),min(ah[j],bh[j])-max(al[j],bl[j]))
            c=intersect(a,b); cuts=subtract(a,b); joined=union(a,b)
            with self.subTest(case=i):
                self.assertEqual(volume(c),expected)
                self.assertEqual(volume(intersect(b,a)),expected)
                self.assertEqual(total_volume(cuts),volume(a)-expected)
                self.assertEqual(total_volume(joined),volume(a)+volume(b)-expected)
                for s in [c,*cuts,*joined]: self.assertEqual(validate(s),[])
                for j,left in enumerate(cuts):
                    for right in cuts[j+1:]: self.assertEqual(volume(intersect(left,right)),0)


    def test_validator_rejects_broken_boundaries(self):
        a=Solid.box((0,0,0),(1,1,1))
        self.assertTrue(validate(Solid(a.faces[:-1])))
        self.assertTrue(validate(Solid((tuple(reversed(a.faces[0])),)+a.faces[1:])))
        self.assertTrue(validate(Solid(a.faces+(a.faces[0],))))

    def test_general_rotated_corpus(self):
        from kernel import point, dot, sub, plane
        rng=random.Random(1102026)
        def rotation(q):
            w,x,y,z=map(F,q); n=w*w+x*x+y*y+z*z
            return (((w*w+x*x-y*y-z*z)/n,2*(x*y-w*z)/n,2*(x*z+w*y)/n),
                    (2*(x*y+w*z)/n,(w*w-x*x+y*y-z*z)/n,2*(y*z-w*x)/n),
                    (2*(x*z-w*y)/n,2*(y*z+w*x)/n,(w*w-x*x-y*y+z*z)/n))
        def in_transformed_cube(p,m,t):
            # Independent inverse transform membership, no clipping/face routines.
            local=tuple(sum(m[k][j]*(p[k]-t[k]) for k in range(3)) for j in range(3))
            return all(-1<x<1 for x in local)
        def in_result(p,s):
            return bool(s.faces) and all(dot(n,p)<=d for n,d in map(plane,s.faces))
        a=Solid.box((-1,-1,-1),(1,1,1))
        for case in range(24):
            m=rotation([rng.randrange(1,7) for _ in range(4)])
            t=point(tuple(F(rng.randrange(-6,7),4) for _ in range(3)))
            b=a.affine(m,t); c=intersect(a,b)
            cuts=subtract(a,b); joined=union(a,b)
            with self.subTest(case=case):
                self.assertEqual(volume(c),volume(intersect(b,a)))
                self.assertLessEqual(volume(c),8)
                self.assertEqual(total_volume(cuts)+volume(c),8)
                self.assertEqual(total_volume(joined)+volume(c),16)
                for s in [b,c,*cuts,*joined]: self.assertEqual(validate(s),[])
                # Sample points avoid boundary ambiguities via unequal prime denominators.
                for sample in range(20):
                    p=point((F(rng.randrange(-170,171),101),
                             F(rng.randrange(-180,181),103),
                             F(rng.randrange(-190,191),107)))
                    # Regularized difference has boundary conventions; test interiors here.
                    if any(dot(n,p)==d for n,d in map(plane,a.faces+b.faces)): continue
                    ina=all(-1<x<1 for x in p); inb=in_transformed_cube(p,m,t)
                    self.assertEqual(in_result(p,c),ina and inb)
                    self.assertEqual(any(in_result(p,s) for s in cuts),ina and not inb)
                    self.assertEqual(any(in_result(p,s) for s in joined),ina or inb)


    def test_internal_partition_boundary_is_not_a_gap(self):
        from kernel import plane, dot
        a=Solid.box((-1,-1,-1),(1,1,1))
        b=Solid.box((0,-1,-1),(2,1,1))
        cells=union(a,b); p=(F(1),F(0),F(0))
        self.assertTrue(any(all(dot(n,p)<=d for n,d in map(plane,c.faces)) for c in cells))
        # The point is on a shared cell face, although inside the overall union.
        self.assertFalse(any(all(dot(n,p)<d for n,d in map(plane,c.faces)) for c in cells))

if __name__=="__main__": unittest.main()
