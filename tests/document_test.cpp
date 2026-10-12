#include "document_fixtures.hpp"
#include "test.hpp"
#include <numbers>
int main(){
 using namespace cad;
 auto initial=recompute(fixtureDocument());CHECK(initial);CHECK(near(volume(initial.value().features[2].shape),8000-90*std::numbers::pi));
 auto edited=initial.value();changeWidth(edited,50);
 auto updated=recompute(edited,{"sketch"});CHECK(updated);
 CHECK(near(volume(updated.value().features[2].shape),10000-90*std::numbers::pi));
 CHECK(updated.value().features[3].sketch.profile.vertices==initial.value().features[3].sketch.profile.vertices);
 for(size_t i=0;i<4;++i)CHECK(updated.value().features[i].id==initial.value().features[i].id);
 DocumentSession session(initial.value());CHECK(session.begin());CHECK(session.replace(updated.value()));CHECK(session.commit());
 CHECK(session.current().revision==1);CHECK(session.persistedFeatureIds().size()==4);
 CHECK(session.undo());CHECK(near(volume(session.current().features[2].shape),8000-90*std::numbers::pi));CHECK(session.current().revision==2);
 CHECK(session.redo());CHECK(near(volume(session.current().features[2].shape),10000-90*std::numbers::pi));CHECK(session.current().revision==3);
 CHECK(session.begin());auto bad=session.current();std::get<ExtrudeParams>(bad.features[1].parameters).depth=-1;
 CHECK(session.replace(bad));auto failed=session.commit();CHECK(!failed);CHECK(failed.error().entityIds.front()=="extrude");session.abort();
 CHECK(session.current().revision==3);
 auto cyclic=fixtureDocument();cyclic.features[0].inputIds={"hole"};
 auto c=recompute(cyclic);CHECK(!c);CHECK(c.error().code=="DependencyCycle");
 auto mismatch=fixtureDocument();mismatch.features[1].inputIds={};CHECK(!recompute(mismatch));
}
