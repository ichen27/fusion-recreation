#include "cad/sketch.hpp"
#include "test.hpp"
#include "fixtures.hpp"
#include <iostream>
int main(){
 using namespace cad;
 auto sketch=rectangleSketch();auto r=solve(sketch);
 CHECK(r); CHECK(r.value().degreesOfFreedom==0); CHECK(r.value().profile.closed);
 CHECK(near(r.value().profile.vertices[1].x,40)); CHECK(r.value().maxResidual<1e-7);
 auto loose=sketch;loose.constraints.erase(loose.constraints.end()-2);
 auto l=solve(loose);CHECK(l);CHECK(l.value().degreesOfFreedom>0);
 Sketch circle{{CircleEntity{"circle",{0,0},2}},{{"radius",ConstraintKind::Radius,{"circle"},3}}};
 auto c=solve(circle);CHECK(c);CHECK(near(c.value().circles[0].radius,3));
 auto conflict=sketch;conflict.constraints.push_back({"badWidth",ConstraintKind::Distance,{"bottom"},50});
 auto bad=solve(conflict);CHECK(!bad);CHECK(bad.error().code=="ConstraintConflict");CHECK(!bad.error().entityIds.empty());
 CHECK(std::get<Line>(conflict.entities[0]).b.x==40);
 auto duplicate=sketch;duplicate.constraints.push_back({"duplicate",ConstraintKind::Distance,{"bottom"},40});
 auto d=solve(duplicate);CHECK(d);CHECK(!d.value().redundantIds.empty());
 auto zero=sketch;std::get<Line>(zero.entities[0]).b={0,0};CHECK(!solve(zero));
 auto invalid=sketch;invalid.constraints[0].entityIds={"missing","right:start"};CHECK(!solve(invalid));
 std::cout<<"planeGCS FreeCAD 4fd3bf3; max residual "<<r.value().maxResidual<<"\n";
}
