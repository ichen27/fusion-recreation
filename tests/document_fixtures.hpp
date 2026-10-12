#pragma once
#include "cad/document.hpp"
#include "fixtures.hpp"
inline cad::Document fixtureDocument(){
 using namespace cad;
 return {"document",Units::Millimeter,0,{
 {"sketch",FeatureKind::Sketch,{},rectangleSketch()},
 {"extrude",FeatureKind::Extrude,{"sketch"},ExtrudeParams{"sketch",10}},
 {"hole",FeatureKind::Hole,{"extrude"},HoleParams{"extrude",{"extrude","top",{"extrude/top"}},3}},
 {"independent",FeatureKind::Sketch,{},rectangleSketch(12,7)}
 }};
}
inline void changeWidth(cad::Document& d,double width){
 auto& s=std::get<cad::Sketch>(d.features[0].parameters);
 for(auto& c:s.constraints)if(c.id=="width")c.value=width;
}
