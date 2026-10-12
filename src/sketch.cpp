#include "cad/sketch.hpp"
#include "GCS.h"
#include <cmath>
#include <deque>
#include <map>
#include <set>
#include <algorithm>
namespace cad {
namespace {
bool coordinate(double v){return std::isfinite(v)&&std::abs(v)<=1e6;}
bool pointValid(Point2 p){return coordinate(p.x)&&coordinate(p.y);}
struct Working {Id id;bool line=false,construction=false;double x,y,u,v;};
}
Result<SketchSolution> solve(const Sketch& sketch){
 if(sketch.entities.empty()||sketch.entities.size()>1024||sketch.constraints.size()>4096)
  return fail("InvalidSketch","Expected 1..1024 entities and at most 4096 constraints");
 std::vector<Working> w;w.reserve(sketch.entities.size());
 std::set<Id> ids;
 for(const auto& e:sketch.entities){
  auto check=std::visit([&](const auto& a)->Result<void>{
   if(a.id.empty()||a.id.find(':')!=Id::npos||!ids.insert(a.id).second)
    return fail("InvalidId","Entity IDs must be unique, nonempty and contain no colon",{a.id});
   using T=std::decay_t<decltype(a)>;
   if constexpr(std::is_same_v<T,Line>){
    if(!pointValid(a.a)||!pointValid(a.b)||std::hypot(a.a.x-a.b.x,a.a.y-a.b.y)<=1e-7)
     return fail("InvalidProfile","Invalid or zero-length sketch line",{a.id});
    w.push_back({a.id,true,a.construction,a.a.x,a.a.y,a.b.x,a.b.y});
   }else{
    if(!pointValid(a.center)||!coordinate(a.radius)||a.radius<=1e-7)
     return fail("InvalidDimension","Invalid radius or center",{a.id});
    if constexpr(std::is_same_v<T,Arc>){
     return fail("UnsupportedEntity","Arc solving and curved profile extraction are not implemented",{a.id});
    }
    w.push_back({a.id,false,a.construction,a.center.x,a.center.y,a.radius,0});
   }
   return {};
  },e);
  if(!check)return check.error();
 }
 GCS::System sys;GCS::VEC_pD unknowns;
 std::map<Id,GCS::Point> points;std::map<Id,Working*> entities;
 for(auto& e:w){
  entities[e.id]=&e;points[e.id+(e.line?":start":":center")]=GCS::Point(&e.x,&e.y);
  unknowns.push_back(&e.x);unknowns.push_back(&e.y);unknowns.push_back(&e.u);
  if(e.line){unknowns.push_back(&e.v);points[e.id+":end"]=GCS::Point(&e.u,&e.v);}
 }
 std::deque<double> constants;
 auto constant=[&](double v){constants.push_back(v);return &constants.back();};
 auto getPoint=[&](const Id& id)->GCS::Point*{auto it=points.find(id);return it==points.end()?nullptr:&it->second;};
 std::set<Id> constraintIds;
 for(size_t i=0;i<sketch.constraints.size();++i){
  const auto& c=sketch.constraints[i];int tag=int(i+1);
  if(c.id.empty()||!constraintIds.insert(c.id).second||!coordinate(c.value))
   return fail("InvalidConstraint","Invalid constraint ID or value",{c.id});
  auto invalid=[&](){return fail("InvalidConstraint","Constraint has invalid entity references or parameters",{c.id});};
  auto refs=c.entityIds;
  Working* e=refs.size()==1&&entities.contains(refs[0])?entities.at(refs[0]):nullptr;
  switch(c.kind){
   case ConstraintKind::Coincident:{
    if(refs.size()!=2||!getPoint(refs[0])||!getPoint(refs[1]))return invalid();
    sys.addConstraintP2PCoincident(*getPoint(refs[0]),*getPoint(refs[1]),tag);break;}
   case ConstraintKind::Horizontal:case ConstraintKind::Vertical:{
    if(!e||!e->line)return invalid();
    auto& a=points.at(e->id+":start");auto& b=points.at(e->id+":end");
    if(c.kind==ConstraintKind::Horizontal)sys.addConstraintHorizontal(a,b,tag);
    else sys.addConstraintVertical(a,b,tag);break;}
   case ConstraintKind::Distance:{
    if(c.value<=1e-7)return invalid();
    if(e&&e->line)sys.addConstraintP2PDistance(points.at(e->id+":start"),points.at(e->id+":end"),constant(c.value),tag);
    else if(refs.size()==2&&getPoint(refs[0])&&getPoint(refs[1]))
     sys.addConstraintP2PDistance(*getPoint(refs[0]),*getPoint(refs[1]),constant(c.value),tag);
    else return invalid();break;}
   case ConstraintKind::Radius:
    if(!e||e->line||c.value<=1e-7)return invalid();
    sys.addConstraintEqual(&e->u,constant(c.value),tag);break;
   case ConstraintKind::FixedPoint:{
    if(refs.size()!=1||!getPoint(refs[0]))return invalid();
    auto p=*getPoint(refs[0]);
    sys.addConstraintEqual(p.x,constant(*p.x),tag);sys.addConstraintEqual(p.y,constant(*p.y),tag);break;}
   default:return fail("UnsupportedConstraint","Unknown constraint kind",{c.id});
  }
 }
 sys.declareUnknowns(unknowns);sys.initSolution();
 GCS::VEC_I conflicts,redundant;sys.getConflicting(conflicts);sys.getRedundant(redundant);
 auto idsFor=[&](const GCS::VEC_I& tags){std::vector<Id> result;for(int tag:tags)if(tag>0&&size_t(tag)<=sketch.constraints.size())result.push_back(sketch.constraints[tag-1].id);return result;};
 if(!conflicts.empty())return fail("ConstraintConflict","Sketch constraints conflict",idsFor(conflicts));
 if(sys.solve()!=GCS::Success)return fail("SolveFailed","Constraint solver did not reach a valid solution");
 sys.applySolution();
 SketchSolution result;result.degreesOfFreedom=sys.dofsNumber();result.redundantIds=idsFor(redundant);
 for(size_t i=0;i<sketch.constraints.size();++i){
  double error=std::abs(sys.calculateConstraintErrorByTag(int(i+1)));
  if(!std::isfinite(error)||error>1e-7)return fail("ConstraintConflict","Constraint residual exceeds tolerance",{sketch.constraints[i].id});
  result.maxResidual=std::max(result.maxResidual,error);
 }
 std::vector<Working*> boundary;
 for(auto& e:w){
  if(!coordinate(e.x)||!coordinate(e.y)||!coordinate(e.u)||!coordinate(e.v))return fail("InvalidDimension","Solved coordinates exceed supported range",{e.id});
  if(e.line){
   if(std::hypot(e.x-e.u,e.y-e.v)<=1e-7)return fail("InvalidProfile","Solved edge collapsed",{e.id});
   if(!e.construction)boundary.push_back(&e);
  }else{
   if(e.u<=1e-7)return fail("InvalidDimension","Solved circle collapsed",{e.id});
   if(!e.construction)result.circles.push_back({{e.x,e.y},e.u});
  }
 }
 // Follow the connected boundary instead of assuming entity storage order.
 if(!boundary.empty()){
  auto* first=boundary.front();Point2 start{first->x,first->y},end{first->u,first->v};
  result.profile.vertices.push_back(start);boundary.erase(boundary.begin());
  auto matches=[](Point2 a,Point2 b){return std::hypot(a.x-b.x,a.y-b.y)<1e-7;};
  while(!boundary.empty()){
   result.profile.vertices.push_back(end);
   auto it=std::find_if(boundary.begin(),boundary.end(),[&](Working* e){return matches(end,{e->x,e->y})||matches(end,{e->u,e->v});});
   if(it==boundary.end())return fail("InvalidProfile","Disconnected or multiple sketch boundaries");
   auto* e=*it;end=matches(end,{e->x,e->y})?Point2{e->u,e->v}:Point2{e->x,e->y};boundary.erase(it);
  }
  result.profile.closed=matches(end,start);
  if(!result.profile.closed)result.profile.vertices.push_back(end);
 }
 return result;
}
}
