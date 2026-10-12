#include "codec.hpp"
#include "native.hpp"
#include <BRepTools.hxx>
#include <BRep_Builder.hxx>
#include <sstream>
#include <cmath>
namespace cad {
namespace {
Json point(Point2 p){return Json::array({p.x,p.y});}
Point2 point(const Json& j){
 if(!j.is_array()||j.size()!=2||!j[0].is_number()||!j[1].is_number())throw std::runtime_error("Invalid point");
 Point2 p{j[0].get<double>(),j[1].get<double>()};
 if(!std::isfinite(p.x)||!std::isfinite(p.y))throw std::runtime_error("Nonfinite point");return p;
}
double number(const Json& j){if(!j.is_number())throw std::runtime_error("Expected number");double v=j.get<double>();if(!std::isfinite(v))throw std::runtime_error("Nonfinite number");return v;}
int enumeration(const Json& j,int max){
 if(!j.is_number_integer())throw std::runtime_error("Expected enum integer");auto n=j.get<int64_t>();
 if(n<0||n>max)throw std::runtime_error("Unknown enum");return int(n);
}
Json selection(const Selection& s){return {{"featureId",s.featureId},{"role",s.semanticRole},{"evolutionIds",s.evolutionIds}};}
Selection selection(const Json& j){return {j.at("featureId").get<Id>(),j.at("role").get<std::string>(),j.at("evolutionIds").get<std::vector<Id>>()};}
}
Json encode(const Sketch& s){
 Json es=Json::array(),cs=Json::array();
 for(auto& e:s.entities)std::visit([&](const auto& a){
  Json j={{"id",a.id},{"construction",a.construction}};using T=std::decay_t<decltype(a)>;
  if constexpr(std::is_same_v<T,Line>){j["type"]="line";j["a"]=point(a.a);j["b"]=point(a.b);}
  else{j["type"]=std::is_same_v<T,Arc>?"arc":"circle";j["center"]=point(a.center);j["radius"]=a.radius;
   if constexpr(std::is_same_v<T,Arc>){j["startAngle"]=a.startAngle;j["endAngle"]=a.endAngle;}}
  es.push_back(j);
 },e);
 for(auto& c:s.constraints)cs.push_back({{"id",c.id},{"kind",int(c.kind)},{"entityIds",c.entityIds},{"value",c.value}});
 return {{"entities",es},{"constraints",cs}};
}
Sketch decodeSketch(const Json& j){
 Sketch s;if(!j.at("entities").is_array()||!j.at("constraints").is_array()||j.at("entities").size()>1024||j.at("constraints").size()>4096)throw std::runtime_error("Invalid sketch size");
 for(const auto& e:j.at("entities")){
  auto id=e.at("id").get<Id>();auto type=e.at("type").get<std::string>();bool construction=e.at("construction").get<bool>();
  if(type=="line")s.entities.push_back(Line{id,point(e.at("a")),point(e.at("b")),construction});
  else if(type=="circle")s.entities.push_back(CircleEntity{id,point(e.at("center")),number(e.at("radius")),construction});
  else if(type=="arc")s.entities.push_back(Arc{id,point(e.at("center")),number(e.at("radius")),number(e.at("startAngle")),number(e.at("endAngle")),construction});
  else throw std::runtime_error("Unknown entity");
 }
 for(const auto& c:j.at("constraints"))s.constraints.push_back({c.at("id").get<Id>(),ConstraintKind(enumeration(c.at("kind"),5)),c.at("entityIds").get<std::vector<Id>>(),number(c.at("value"))});
 return s;
}
Json encode(const Document& d){
 Json fs=Json::array();
 for(auto& f:d.features){
  Json p;
  std::visit([&](const auto& a){
   using T=std::decay_t<decltype(a)>;
   if constexpr(std::is_same_v<T,Sketch>)p=encode(a);
   else if constexpr(std::is_same_v<T,ExtrudeParams>)p={{"profileId",a.profileId},{"depth",a.depth}};
   else if constexpr(std::is_same_v<T,HoleParams>)p={{"baseFeatureId",a.baseFeatureId},{"support",selection(a.support)},{"radius",a.radius},{"centerMode",int(a.centerMode)}};
   else {std::ostringstream brep;BRepTools::Write(Native::get(f.shape),brep);p={{"payloadId",a.payloadId},{"brep",brep.str()}};}
  },f.parameters);
  fs.push_back({{"id",f.id},{"kind",int(f.kind)},{"inputs",f.inputIds},{"parameters",p}});
 }
 return {{"id",d.id},{"units",int(d.units)},{"revision",d.revision},{"features",fs}};
}
Document decodeDocument(const Json& j){
 if(!j.at("revision").is_number_unsigned())throw std::runtime_error("Revision must be unsigned integer");
 if(!j.at("features").is_array()||j.at("features").size()>4096)throw std::runtime_error("Invalid feature list");
 Document d{j.at("id").get<Id>(),Units(enumeration(j.at("units"),1)),j.at("revision").get<Revision>(),{}};
 for(const auto& f:j.at("features")){
  Feature out{f.at("id").get<Id>(),FeatureKind(enumeration(f.at("kind"),3)),f.at("inputs").get<std::vector<Id>>(),Sketch{}};
  const auto& p=f.at("parameters");
  switch(out.kind){
   case FeatureKind::Sketch:out.parameters=decodeSketch(p);break;
   case FeatureKind::Extrude:out.parameters=ExtrudeParams{p.at("profileId").get<Id>(),number(p.at("depth"))};break;
   case FeatureKind::Hole:out.parameters=HoleParams{p.at("baseFeatureId").get<Id>(),selection(p.at("support")),number(p.at("radius")),CenterMode(enumeration(p.at("centerMode"),0))};break;
   case FeatureKind::ImportedBody:{
    out.parameters=ImportedBodyParams{p.at("payloadId").get<Id>()};
    std::istringstream stream(p.at("brep").get<std::string>());TopoDS_Shape shape;BRep_Builder b;BRepTools::Read(shape,stream,b);
    out.shape=Native::wrap(shape);if(!isValid(out.shape))throw std::runtime_error("Invalid BREP payload");break;}
  }
  d.features.push_back(std::move(out));
 }
 return d;
}
}
