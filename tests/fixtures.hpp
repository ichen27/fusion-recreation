#pragma once
#include "cad/sketch.hpp"
inline cad::Sketch rectangleSketch(double w=40,double h=20){
 using namespace cad;
 return {{{Line{"bottom",{0,0},{w,0}},Line{"right",{w,0},{w,h}},Line{"top",{w,h},{0,h}},Line{"left",{0,h},{0,0}}}},
 {{"c1",ConstraintKind::Coincident,{"bottom:end","right:start"}},
 {"c2",ConstraintKind::Coincident,{"right:end","top:start"}},
 {"c3",ConstraintKind::Coincident,{"top:end","left:start"}},
 {"c4",ConstraintKind::Coincident,{"left:end","bottom:start"}},
 {"h1",ConstraintKind::Horizontal,{"bottom"}},{"h2",ConstraintKind::Horizontal,{"top"}},
 {"v1",ConstraintKind::Vertical,{"left"}},{"v2",ConstraintKind::Vertical,{"right"}},
 {"origin",ConstraintKind::FixedPoint,{"bottom:start"}},
 {"width",ConstraintKind::Distance,{"bottom"},w},{"height",ConstraintKind::Distance,{"right"},h}}};
}
