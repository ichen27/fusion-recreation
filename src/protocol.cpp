#include "protocol.hpp"
#include <cmath>
namespace cad {
namespace {
const std::vector<std::string> names={"CreateSketch","Extrude","Hole","EditSketch","Undo","Redo"};
double number(const Json& j){if(!j.is_number())throw std::runtime_error("Expected numeric parameter");double n=j.get<double>();if(!std::isfinite(n))throw std::runtime_error("Expected finite parameter");return n;}
}
Json encode(const Command& c){
 if(size_t(c.operation)>=names.size())throw std::runtime_error("Unknown operation");
 Json p=Json::object();
 std::visit([&](const auto& a){
  using T=std::decay_t<decltype(a)>;
  if constexpr(std::is_same_v<T,SketchCommand>)p={{"featureId",a.featureId},{"sketch",encode(a.sketch)}};
  else if constexpr(std::is_same_v<T,ExtrudeCommand>)p={{"featureId",a.featureId},{"profileId",a.parameters.profileId},{"depth",a.parameters.depth}};
  else if constexpr(std::is_same_v<T,HoleCommand>){
   auto& h=a.parameters;p={{"featureId",a.featureId},{"baseFeatureId",h.baseFeatureId},{"radius",h.radius},{"centerMode",int(h.centerMode)},
    {"support",{{"featureId",h.support.featureId},{"role",h.support.semanticRole},{"evolutionIds",h.support.evolutionIds}}}};
  }
 },c.parameters);
 return {{"documentId",c.documentId},{"expectedRevision",c.expectedRevision},{"transactionId",c.transactionId},{"operation",names.at(size_t(c.operation))},{"parameters",p}};
}
Command decodeCommand(const Json& j){
 if(!j.at("expectedRevision").is_number_unsigned())throw std::runtime_error("expectedRevision must be an unsigned integer");
 auto op=j.at("operation").get<std::string>();auto it=std::find(names.begin(),names.end(),op);
 if(it==names.end())throw std::runtime_error("Unknown operation");
 Command c{j.at("documentId").get<Id>(),j.at("expectedRevision").get<Revision>(),j.at("transactionId").get<Id>(),Operation(it-names.begin()),{}};
 const auto& p=j.at("parameters");
 switch(c.operation){
  case Operation::CreateSketch:case Operation::EditSketch:c.parameters=SketchCommand{p.at("featureId").get<Id>(),decodeSketch(p.at("sketch"))};break;
  case Operation::Extrude:c.parameters=ExtrudeCommand{p.at("featureId").get<Id>(),{p.at("profileId").get<Id>(),number(p.at("depth"))}};break;
  case Operation::Hole:{
   const auto& s=p.at("support");
   if(!p.at("centerMode").is_number_integer()||p.at("centerMode")!=0)throw std::runtime_error("Unsupported centerMode");
   c.parameters=HoleCommand{p.at("featureId").get<Id>(),{p.at("baseFeatureId").get<Id>(),{s.at("featureId").get<Id>(),s.at("role").get<std::string>(),s.at("evolutionIds").get<std::vector<Id>>()},number(p.at("radius"))}};break;}
  case Operation::Undo:case Operation::Redo:if(!p.is_object()||!p.empty())throw std::runtime_error("Undo/Redo parameters must be empty");break;
 }
 return c;
}
Json encode(const Reply& r){return {{"ok",true},{"revision",r.committedRevision},{"affectedFeatureIds",r.affectedFeatureIds}};}
Json errorReply(const Diagnostic& e){return {{"ok",false},{"error",{{"code",e.code},{"message",e.message},{"entityIds",e.entityIds}}}};}
}
