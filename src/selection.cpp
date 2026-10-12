#include "cad/document.hpp"
#include <algorithm>
namespace cad {
Result<Id> resolve(const Document& d,const Selection& s){
 auto* f=findFeature(d,s.featureId);
 if(!f)return fail("BrokenReference","Referenced feature no longer exists",{s.featureId});
 auto it=f->topology.find(s.semanticRole);
 if(it==f->topology.end()||it->second.empty())return fail("BrokenReference","Semantic support no longer exists",{s.featureId});
 if(it->second.size()!=1)return fail("AmbiguousReference","Support has multiple descendants; explicit repair is required",{s.featureId});
 const auto& id=it->second.front();
 if(!s.evolutionIds.empty()&&std::find(s.evolutionIds.begin(),s.evolutionIds.end(),id)==s.evolutionIds.end())
  return fail("BrokenReference","Support provenance does not match",{s.featureId});
 return id;
}
}
