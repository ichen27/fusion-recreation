#include "document_fixtures.hpp"
#include "test.hpp"
int main() {
  using namespace cad;
  auto d = recompute(fixtureDocument());
  CHECK(d);
  Selection top{"extrude", "top", {"extrude/top"}};
  auto a = resolve(d.value(), top);
  CHECK(a);
  auto edit = d.value();
  changeWidth(edit, 50);
  auto e = recompute(edit, {"sketch"});
  CHECK(e);
  auto b = resolve(e.value(), top);
  CHECK(b);
  CHECK(a.value() == b.value());
  auto split = e.value();
  split.features[1].topology["top"] = {"extrude/top/a", "extrude/top/b"};
  auto ambiguous = resolve(split, top);
  CHECK(!ambiguous);
  CHECK(ambiguous.error().code == "AmbiguousReference");
  auto deleted = e.value();
  deleted.features[1].topology.erase("top");
  auto broken = resolve(deleted, top);
  CHECK(!broken);
  CHECK(broken.error().code == "BrokenReference");
  auto invalid = fixtureDocument();
  std::get<HoleParams>(invalid.features[2].parameters).support.semanticRole = "missing";
  auto bad = recompute(invalid);
  CHECK(!bad);
  CHECK(bad.error().entityIds.front() == "hole");
}
