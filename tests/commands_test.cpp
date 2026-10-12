#include "cad/commands.hpp"
#include "fixtures.hpp"
#include "test.hpp"
#include <unistd.h>
int main(){
 using namespace cad;namespace fs=std::filesystem;
 auto path=fs::temp_directory_path()/("cad-commands-"+std::to_string(getpid()));fs::remove_all(path);
 CommandStore store(path,"doc");
 Command command{"doc",0,"tx1",Operation::CreateSketch,SketchCommand{"s",rectangleSketch()}};
 auto first=store.apply(command);CHECK(first);CHECK(first.value().committedRevision==1);
 auto duplicate=store.apply(command);CHECK(duplicate);CHECK(duplicate.value().committedRevision==1);
 auto conflict=command;conflict.parameters=SketchCommand{"other",rectangleSketch()};
 auto r=store.apply(conflict);CHECK(!r);CHECK(r.error().code=="TransactionConflict");
 auto stale=command;stale.transactionId="tx2";r=store.apply(stale);CHECK(!r);CHECK(r.error().code=="RevisionConflict");
 CommandStore reopened(path,"doc");r=reopened.apply(command);CHECK(r);CHECK(r.value().committedRevision==1);
 r=reopened.apply({"doc",1,"undo",Operation::Undo,{}});CHECK(r);CHECK(r.value().committedRevision==2);
 CHECK(reopened.snapshot().value().document.features.empty());
 r=reopened.apply({"doc",2,"redo",Operation::Redo,{}});CHECK(r);CHECK(r.value().committedRevision==3);
 CHECK(reopened.snapshot().value().document.features.size()==1);
 auto invalid=command;invalid.transactionId="invalid";invalid.expectedRevision=3;
 std::get<SketchCommand>(invalid.parameters).sketch.constraints.back().value=-1;
 CHECK(!reopened.apply(invalid));CHECK(reopened.snapshot().value().document.revision==3);
 fs::remove_all(path);
}
