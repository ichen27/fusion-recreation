#include "cad/kernel.hpp"
#include "test.hpp"
#include <limits>
using namespace cad;
Profile rectangle(double w,double h){return {{{0,0},{w,0},{w,h},{0,h}},true};}
int main(){
 auto base=extrude(rectangle(40,20),10); CHECK(base); CHECK(isValid(base.value())); CHECK(near(volume(base.value()),8000));
 auto hole=cutCylinder(base.value(),{{20,10},3},10); CHECK(hole); CHECK(isValid(hole.value()));
 CHECK(near(volume(hole.value()),8000-90*std::acos(-1)));
 for(double d:{0.,-1.,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
  auto bad=extrude(rectangle(40,20),d); CHECK(!bad); CHECK(bad.error().code=="InvalidDimension");
  auto cut=cutCylinder(base.value(),{{20,10},3},d); CHECK(!cut); CHECK(cut.error().code=="InvalidDimension");
 }
 auto open=rectangle(40,20); open.closed=false;
 std::vector<Profile> invalid={open,{{{0,0},{10,10},{0,10},{10,0}},true},{{{0,0},{0,0},{1,1}},true},
 {{{0,0},{1,0},{std::numeric_limits<double>::infinity(),1}},true},
 {{{0,0},{1,0},{1,std::numeric_limits<double>::quiet_NaN()}},true}};
 for(auto p:invalid){auto r=extrude(p,10);CHECK(!r);CHECK(r.error().code=="InvalidProfile");}
 CHECK(!cutCylinder(base.value(),{{20,10},0},10));
 CHECK(!cutCylinder(base.value(),{{std::numeric_limits<double>::quiet_NaN(),10},3},10));
 std::cout<<"kernel: valid extrusion and cut; invalid dimensions/profiles rejected\n";
}
