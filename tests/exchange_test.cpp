#include "cad/exchange.hpp"
#include "cad/storage.hpp"
#include "document_fixtures.hpp"
#include "native.hpp"
#include "test.hpp"
#include <BRepBuilderAPI_Transform.hxx>
#include <fstream>
#include <gp_Trsf.hxx>
#include <unistd.h>
int main() {
  using namespace cad;
  namespace fs = std::filesystem;
  auto dir = fs::temp_directory_path() / ("cad-exchange-" + std::to_string(getpid()));
  fs::create_directories(dir);
  auto base = recompute(fixtureDocument());
  CHECK(base);
  gp_Trsf tr;
  tr.SetTranslation(gp_Vec(100, 30, 7));
  auto moved = Native::wrap(
      BRepBuilderAPI_Transform(Native::get(base.value().features[2].shape), tr, true).Shape());
  Document d{"placed",
             Units::Millimeter,
             0,
             {{"body", FeatureKind::ImportedBody, {}, ImportedBodyParams{"payload"}}}};
  d.features[0].shape = moved;
  for (auto units : {Units::Millimeter, Units::Inch}) {
    d.units = units;
    auto file = dir / (units == Units::Inch ? "inch.step" : "mm.step");
    CHECK(exportStep(d, file));
    if (units == Units::Inch) {
      std::ifstream step(file);
      std::string bytes((std::istreambuf_iterator<char>(step)), {});
      CHECK(bytes.find("INCH") != std::string::npos);
      CHECK(bytes.find("CONVERSION_BASED_UNIT") != std::string::npos);
    }
    auto r = importStep(file);
    CHECK(r);
    CHECK(!r.value().losses.empty());
    const auto &imported = r.value().document.features[0].shape;
    CHECK(near(volume(imported), volume(moved)));
    auto a = bounds(moved), b = bounds(imported);
    for (int i = 0; i < 6; ++i)
      CHECK(near(a[i], b[i]));
    CHECK(save(r.value().document, dir / "saved"));
    auto reopened = load(dir / "saved");
    CHECK(reopened);
    CHECK(near(volume(reopened.value().features[0].shape), volume(moved)));
  }
  fs::remove_all(dir);
}
