#include "cad/exchange.hpp"
#include "native.hpp"
#include <BRep_Builder.hxx>
#include <Interface_Static.hxx>
#include <STEPControl_Reader.hxx>
#include <STEPControl_Writer.hxx>
#include <TopoDS_Compound.hxx>
#include <chrono>
#include <mutex>
#include <set>
namespace cad {
namespace {
std::mutex exchangeMutex;
}
Result<void> exportStep(const Document &input, const std::filesystem::path &path) {
  std::lock_guard lock(exchangeMutex);
  try {
    auto r = recompute(input);
    if (!r)
      return r.error();
    const auto &d = r.value();
    std::set<Id> consumed;
    for (auto &f : d.features)
      for (auto &id : f.inputIds)
        consumed.insert(id);
    TopoDS_Compound compound;
    BRep_Builder builder;
    builder.MakeCompound(compound);
    int count = 0;
    for (auto &f : d.features)
      if (f.kind != FeatureKind::Sketch && !consumed.contains(f.id) && isValid(f.shape)) {
        builder.Add(compound, Native::get(f.shape));
        ++count;
      }
    if (!count)
      return fail("EmptyExport", "No terminal solid bodies");
    STEPControl_Writer writer;
    Interface_Static::SetCVal("write.step.unit", d.units == Units::Inch ? "INCH" : "MM");
    if (writer.Transfer(compound, STEPControl_AsIs) != IFSelect_RetDone)
      return fail("StepFailure", "STEP transfer failed");
    if (writer.Write(path.c_str()) != IFSelect_RetDone)
      return fail("StepFailure", "STEP write failed");
    return {};
  } catch (const Standard_Failure &e) {
    return fail("StepFailure", e.what());
  } catch (const std::exception &e) {
    return fail("StepFailure", e.what());
  }
}
Result<ImportResult> importStep(const std::filesystem::path &path) {
  std::lock_guard lock(exchangeMutex);
  try {
    STEPControl_Reader reader;
    if (reader.ReadFile(path.c_str()) != IFSelect_RetDone)
      return fail("StepFailure", "STEP read failed");
    reader.SetSystemLengthUnit(1.0); // internal length unit is one millimeter
    if (reader.TransferRoots() == 0)
      return fail("StepFailure", "STEP file has no transferable roots");
    auto shape = Native::wrap(reader.OneShape());
    if (!isValid(shape))
      return fail("StepFailure", "Imported shape is invalid");
    auto id =
        "import-" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
    Document d{
        id,
        Units::Millimeter,
        0,
        {{id + "/body", FeatureKind::ImportedBody, {}, ImportedBodyParams{id + "/payload"}}}};
    d.features[0].shape = shape;
    auto valid = recompute(d);
    if (!valid)
      return valid.error();
    return ImportResult{valid.value(),
                        {"Parametric feature history is unavailable",
                         "Assembly hierarchy, names, colors and other presentation metadata are "
                         "not retained; occurrence transforms are baked into geometry"}};
  } catch (const Standard_Failure &e) {
    return fail("StepFailure", e.what());
  } catch (const std::exception &e) {
    return fail("StepFailure", e.what());
  }
}
} // namespace cad
