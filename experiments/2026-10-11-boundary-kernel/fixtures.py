"""Reproducible flat-face workflows; no vendor model assets."""
from fractions import Fraction as F
from kernel import Solid

def box(lo,hi): return Solid.box(lo,hi)
def workflows():
    a=box((0,0,0),(4,4,2)); hole=box((1,1,-1),(3,3,3))
    small=box((0,0,0),(1,1,1))
    cube=box((-1,-1,-1),(1,1,1))
    rotated=cube.affine(((F(3,5),-F(4,5),0),(F(4,5),F(3,5),0),(0,0,1)),(F(1,3),F(1,7),F(1,5)))
    cases=[
        ("overlap_union",box((0,0,0),(2,2,2)),[("union",box((1,0,0),(3,2,2)))]),
        ("face_contact",small,[("union",box((1,0,0),(2,1,1)))]),
        ("l_shape",box((0,0,0),(2,1,1)),[("union",box((0,0,0),(1,2,1)))]),
        ("step_partial_contact",box((0,0,0),(2,2,1)),[("union",box((1,0,1),(2,1,2)))]),
        ("cavity",box((0,0,0),(4,4,4)),[("cut",box((1,1,1),(3,3,3)))]),
        ("through_hole",a,[("cut",hole)]),
        ("disconnected",small,[("union",box((2,0,0),(3,1,1)))]),
        ("split",box((0,0,0),(3,1,1)),[("cut",box((1,-1,-1),(2,2,2)))]),
        ("repeat_restore",a,[("cut",box((1,1,-1),(2,2,3))),
                            ("cut",box((2,1,-1),(3,2,3))),
                            ("cut",box((1,1,-1),(2,2,3))),
                            ("union",box((1,1,0),(3,2,2)))]),
        ("cut_then_intersect",a,[("cut",hole),("intersection",box((0,0,0),(2,4,2)))]),
        ("two_holes",box((0,0,0),(6,4,2)),[("cut",box((1,1,-1),(2,3,3))),("cut",box((4,1,-1),(5,3,3)))]),
        ("rotated_union_cut",cube,[("union",rotated),("cut",rotated)]),
        ("rotated_intersection",cube,[("intersection",rotated)]),
        ("thin_wall_1e-4",small,[("cut",box((F(1,10000),-1,-1),(2,2,2)))]),
    ]
    return cases
