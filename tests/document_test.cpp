#include "document_fixtures.hpp"
#include "native.hpp"
#include "test.hpp"
#include <BRepAdaptor_Surface.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <numbers>
void checkHoleCenter(const cad::Shape &shape, double x, double y) {
  int cylinders = 0;
  for (TopExp_Explorer faces(cad::Native::get(shape), TopAbs_FACE); faces.More(); faces.Next()) {
    BRepAdaptor_Surface surface(TopoDS::Face(faces.Current()));
    if (surface.GetType() == GeomAbs_Cylinder) {
      const auto axis = surface.Cylinder().Axis();
      CHECK(near(axis.Location().X(), x));
      CHECK(near(axis.Location().Y(), y));
      CHECK(near(surface.Cylinder().Radius(), 3));
      ++cylinders;
    }
  }
  CHECK(cylinders == 1);
}
int main() {
  using namespace cad;
  auto initial = recompute(fixtureDocument());
  CHECK(initial);
  CHECK(near(volume(initial.value().features[2].shape), 8000 - 90 * std::numbers::pi));
  checkHoleCenter(initial.value().features[2].shape, 20, 10);
  auto edited = initial.value();
  changeWidth(edited, 50);
  auto updated = recompute(edited, {"sketch"});
  CHECK(updated);
  checkHoleCenter(updated.value().features[2].shape, 25, 10);
  CHECK(near(volume(updated.value().features[2].shape), 10000 - 90 * std::numbers::pi));
  CHECK(updated.value().features[3].sketch.profile.vertices ==
        initial.value().features[3].sketch.profile.vertices);
  for (size_t i = 0; i < 4; ++i)
    CHECK(updated.value().features[i].id == initial.value().features[i].id);
  DocumentSession session(initial.value());
  CHECK(session.begin());
  CHECK(session.replace(updated.value()));
  CHECK(session.commit());
  CHECK(session.current().revision == 1);
  CHECK(session.persistedFeatureIds().size() == 4);
  CHECK(session.undo());
  CHECK(near(volume(session.current().features[2].shape), 8000 - 90 * std::numbers::pi));
  CHECK(session.current().revision == 2);
  CHECK(session.redo());
  CHECK(near(volume(session.current().features[2].shape), 10000 - 90 * std::numbers::pi));
  CHECK(session.current().revision == 3);
  CHECK(session.begin());
  auto bad = session.current();
  std::get<ExtrudeParams>(bad.features[1].parameters).depth = -1;
  CHECK(session.replace(bad));
  auto failed = session.commit();
  CHECK(!failed);
  CHECK(failed.error().entityIds.front() == "extrude");
  session.abort();
  CHECK(session.current().revision == 3);
  auto cyclic = fixtureDocument();
  cyclic.features[0].inputIds = {"hole"};
  auto c = recompute(cyclic);
  CHECK(!c);
  CHECK(c.error().code == "DependencyCycle");
  auto mismatch = fixtureDocument();
  mismatch.features[1].inputIds = {};
  CHECK(!recompute(mismatch));
}
