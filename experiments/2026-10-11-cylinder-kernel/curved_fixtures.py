"""Fixed analytic examples and reproducible generated parallel-axis workflows."""
import random
from curves import Disk,Rect
def workflows():
    block=(Rect(-10,-10,10,10),0,10)
    cases=[
      ("cylinder",(Disk(0,0,3),0,10),[]),
      ("through_hole",(Rect(0,0,40,20),0,10),[("cut",(Disk(20,10,3),-1,11))]),
      ("blind_hole",block,[("cut",(Disk(0,0,3),6,11))]),
      ("counterbore",block,[("cut",(Disk(0,0,2),-1,11)),("cut",(Disk(0,0,4),7,11))]),
      ("overlapping_holes",block,[("cut",(Disk(0,0,2),-1,11)),("cut",(Disk(2,0,2),-1,11))]),
      ("partial_depth_overlap",block,[("cut",(Disk(0,0,2),2,11)),("cut",(Disk(2,0,2),6,11))]),
      ("cylinder_union",(Disk(0,0,2),0,4),[("union",(Disk(2,0,2),1,5))]),
      ("cylinder_intersection",(Disk(0,0,2),0,4),[("intersection",(Disk(2,0,2),1,5))]),
      ("external_breakout",(Rect(0,-3,4,3),0,2),[("cut",(Disk(0,0,2),-1,3))]),
      ("disconnected",(Disk(-3,0,1),0,2),[("union",(Disk(3,0,1),0,2))]),
      ("tube",(Disk(0,0,3),0,10),[("cut",(Disk(0,0,1),-1,11))]),
      ("closed_cavity",block,[("cut",(Disk(0,0,2),2,7))]),
      ("repeat_and_restore",block,[("cut",(Disk(0,0,2),-1,11)),("cut",(Disk(0,0,2),-1,11)),("union",(Disk(0,0,2),0,10))]),
    ]
    rng=random.Random(10112026)
    for i in range(8):
        x=rng.uniform(-3,3); y=rng.uniform(-3,3)
        r=rng.uniform(1.1,2.0); s=rng.uniform(1.2,2.1)
        first=(Disk(x,y,r),rng.uniform(1,4),11)
        second=(Disk(x+1.4,y+.3,s),rng.uniform(4.5,7),11)
        cases.append((f"generated_{i}",block,[("cut",first),("cut",second)]))
    return cases
