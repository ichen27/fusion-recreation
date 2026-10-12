#include "cad/document.hpp"
#include "native.hpp"
#include <BRepAdaptor_Surface.hxx>
#include <BRepTools.hxx>
#include <TDF_ChildIterator.hxx>
#include <TDataStd_AsciiString.hxx>
#include <TDocStd_Document.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <functional>
#include <limits>
#include <numbers>
#include <set>
namespace cad {
const Feature *findFeature(const Document &d, const Id &id) {
  for (const auto &f : d.features)
    if (f.id == id)
      return &f;
  return nullptr;
}
namespace {
void mapTop(Feature &f) {
  f.topology.clear();
  auto b = bounds(f.shape);
  int count = 0;
  for (TopExp_Explorer ex(Native::get(f.shape), TopAbs_FACE); ex.More(); ex.Next()) {
    BRepAdaptor_Surface s(TopoDS::Face(ex.Current()));
    if (s.GetType() == GeomAbs_Plane) {
      auto plane = s.Plane();
      if (std::abs(plane.Axis().Direction().Z()) > 1 - 1e-9 &&
          std::abs(plane.Location().Z() - b[5]) < 1e-7)
        ++count;
    }
  }
  if (count == 1)
    f.topology["top"] = {f.id + "/top"};
  else
    for (int i = 0; i < count; ++i)
      f.topology["top"].push_back(f.id + "/top/split" + std::to_string(i));
}
} // namespace
Result<Document> recompute(const Document &input, const std::vector<Id> &changed) {
  if (input.id.empty() || input.features.size() > 4096)
    return fail("InvalidDocument", "Document ID required; feature limit is 4096");
  if (input.units != Units::Millimeter && input.units != Units::Inch)
    return fail("InvalidUnits", "Unknown document units");
  Document d = input;
  std::map<Id, size_t> index;
  for (size_t i = 0; i < d.features.size(); ++i)
    if (d.features[i].id.empty() || !index.emplace(d.features[i].id, i).second)
      return fail("InvalidId", "Feature IDs must be unique", {d.features[i].id});
  std::vector<int> state(d.features.size());
  std::vector<size_t> order;
  std::function<Result<void>(size_t)> visit = [&](size_t i) -> Result<void> {
    if (state[i] == 1)
      return fail("DependencyCycle", "Feature dependency cycle", {d.features[i].id});
    if (state[i] == 2)
      return {};
    state[i] = 1;
    for (const auto &id : d.features[i].inputIds) {
      if (!index.contains(id))
        return fail("BrokenReference", "Missing input feature", {d.features[i].id, id});
      auto r = visit(index.at(id));
      if (!r)
        return r;
    }
    state[i] = 2;
    order.push_back(i);
    return {};
  };
  for (size_t i = 0; i < d.features.size(); ++i) {
    auto r = visit(i);
    if (!r)
      return r.error();
  }
  std::set<Id> dirty(changed.begin(), changed.end());
  for (auto &id : dirty)
    if (!index.contains(id))
      return fail("BrokenReference", "Changed feature does not exist", {id});
  for (auto i : order) {
    auto &f = d.features[i];
    bool needs = changed.empty() || dirty.contains(f.id) || f.status != FeatureStatus::Valid;
    for (auto &id : f.inputIds)
      needs = needs || dirty.contains(id);
    if (!needs)
      continue;
    dirty.insert(f.id);
    auto annotate = [&](Diagnostic e) {
      e.entityIds.insert(e.entityIds.begin(), f.id);
      return e;
    };
    auto inputs = [&](std::vector<Id> expected) { return f.inputIds == expected; };
    if (f.kind == FeatureKind::Sketch && std::holds_alternative<Sketch>(f.parameters)) {
      if (!inputs({}))
        return fail("InvalidInputs", "Sketch has no external dependencies", {f.id});
      auto r = solve(std::get<Sketch>(f.parameters));
      if (!r)
        return annotate(r.error());
      f.sketch = r.value();
      f.topology.clear();
    } else if (f.kind == FeatureKind::Extrude &&
               std::holds_alternative<ExtrudeParams>(f.parameters)) {
      auto p = std::get<ExtrudeParams>(f.parameters);
      if (!inputs({p.profileId}))
        return fail("InvalidInputs", "Extrusion input IDs must match profile", {f.id});
      const auto &base = d.features[index.at(p.profileId)];
      if (base.kind != FeatureKind::Sketch)
        return fail("InvalidInputs", "Extrusion requires a sketch", {f.id});
      if (!base.sketch.circles.empty())
        return fail("UnsupportedProfile",
                    "Circular and mixed extrusion profiles are not implemented", {f.id});
      auto r = extrude(base.sketch.profile, p.depth);
      if (!r)
        return annotate(r.error());
      f.shape = r.value();
      mapTop(f);
    } else if (f.kind == FeatureKind::Hole && std::holds_alternative<HoleParams>(f.parameters)) {
      auto p = std::get<HoleParams>(f.parameters);
      if (!inputs({p.baseFeatureId}) || p.support.featureId != p.baseFeatureId ||
          p.support.semanticRole != "top" || p.centerMode != CenterMode::BodyCenter)
        return fail("InvalidInputs", "Hole requires its base's top support and BodyCenter mode",
                    {f.id});
      auto support = resolve(d, p.support);
      if (!support)
        return annotate(support.error());
      const auto &base = d.features[index.at(p.baseFeatureId)];
      if (!isValid(base.shape))
        return fail("InvalidInputs", "Hole requires a solid", {f.id});
      auto box = bounds(base.shape);
      double depth = box[5] - box[2];
      Circle c{{(box[0] + box[3]) / 2, (box[1] + box[4]) / 2}, p.radius};
      auto r = cutCylinder(base.shape, c, depth);
      if (!r)
        return annotate(r.error());
      double expected = std::numbers::pi * p.radius * p.radius * depth;
      if (std::abs(volume(base.shape) - volume(r.value()) - expected) >
          std::max(1e-6, expected * 1e-8))
        return fail("InvalidHole", "Through hole must lie entirely inside the base", {f.id});
      f.shape = r.value();
      mapTop(f);
    } else if (f.kind == FeatureKind::ImportedBody &&
               std::holds_alternative<ImportedBodyParams>(f.parameters)) {
      if (!inputs({}) || !isValid(f.shape))
        return fail("InvalidImportedBody", "Imported body is missing its geometry", {f.id});
      mapTop(f);
    } else
      return fail("InvalidFeature", "Feature kind and parameters do not match", {f.id});
    f.status = FeatureStatus::Valid;
  }
  return d;
}
struct DocumentSession::Impl {
  Document current, pending;
  bool active = false;
  std::vector<Document> past, future;
  Handle(TDocStd_Document) ocaf = new TDocStd_Document("BinOcaf");
  // Product parameters/history belong to the app; OCAF owns the corresponding
  // label transaction. The monotonic public revision is never rewound by Undo.
  void attributes(const Document &d) {
    ocaf->Main().ForgetAllAttributes(true);
    TDataStd_AsciiString::Set(ocaf->Main(), (d.id + ":" + std::to_string(d.revision)).c_str());
    int i = 1;
    for (const auto &f : d.features) {
      auto label = ocaf->Main().FindChild(i++);
      TDataStd_AsciiString::Set(label, f.id.c_str());
      int j = 1;
      for (const auto &[role, ids] : f.topology)
        for (const auto &id : ids)
          TDataStd_AsciiString::Set(label.FindChild(j++), (role + "=" + id).c_str());
    }
  }
  explicit Impl(Document d) : current(std::move(d)) {
    ocaf->SetUndoLimit(100);
    ocaf->NewCommand();
    attributes(current);
    ocaf->CommitCommand();
    ocaf->ClearUndos();
  }
};
DocumentSession::DocumentSession(Document d) : impl_(std::make_unique<Impl>(std::move(d))) {}
DocumentSession::~DocumentSession() = default;
Result<void> DocumentSession::begin() {
  if (impl_->active)
    return fail("TransactionActive", "Transaction already active");
  impl_->pending = impl_->current;
  impl_->active = true;
  impl_->ocaf->NewCommand();
  return {};
}
Result<void> DocumentSession::replace(Document d) {
  if (!impl_->active)
    return fail("NoTransaction", "Begin a transaction first");
  if (d.id != impl_->current.id)
    return fail("DocumentMismatch", "Cannot replace document identity");
  impl_->pending = std::move(d);
  return {};
}
Result<void> DocumentSession::commit() {
  if (!impl_->active)
    return fail("NoTransaction", "No active transaction");
  auto r = recompute(impl_->pending);
  if (!r)
    return r.error();
  if (impl_->current.revision == std::numeric_limits<Revision>::max())
    return fail("RevisionOverflow", "Revision exhausted");
  auto d = std::move(r.value());
  d.revision = impl_->current.revision + 1;
  impl_->attributes(d);
  impl_->ocaf->CommitCommand();
  impl_->past.push_back(impl_->current);
  if (impl_->past.size() > 100)
    impl_->past.erase(impl_->past.begin());
  impl_->future.clear();
  impl_->current = std::move(d);
  impl_->active = false;
  return {};
}
void DocumentSession::abort() {
  if (impl_->active) {
    impl_->ocaf->AbortCommand();
    impl_->active = false;
  }
}
Result<void> DocumentSession::undo() {
  if (impl_->active)
    return fail("TransactionActive", "Finish transaction before undo");
  if (impl_->past.empty())
    return fail("NothingToUndo", "No previous state");
  if (impl_->current.revision == std::numeric_limits<Revision>::max())
    return fail("RevisionOverflow", "Revision exhausted");
  if (!impl_->ocaf->Undo())
    return fail("HistoryFailure", "OCAF undo failed");
  auto revision = impl_->current.revision + 1;
  impl_->future.push_back(impl_->current);
  impl_->current = impl_->past.back();
  impl_->past.pop_back();
  impl_->current.revision = revision;
  return {};
}
Result<void> DocumentSession::redo() {
  if (impl_->active)
    return fail("TransactionActive", "Finish transaction before redo");
  if (impl_->future.empty())
    return fail("NothingToRedo", "No future state");
  if (impl_->current.revision == std::numeric_limits<Revision>::max())
    return fail("RevisionOverflow", "Revision exhausted");
  if (!impl_->ocaf->Redo())
    return fail("HistoryFailure", "OCAF redo failed");
  auto revision = impl_->current.revision + 1;
  impl_->past.push_back(impl_->current);
  impl_->current = impl_->future.back();
  impl_->future.pop_back();
  impl_->current.revision = revision;
  return {};
}
const Document &DocumentSession::current() const {
  return impl_->current;
}
std::vector<Id> DocumentSession::persistedFeatureIds() const {
  std::vector<Id> ids;
  for (TDF_ChildIterator it(impl_->ocaf->Main()); it.More(); it.Next()) {
    Handle(TDataStd_AsciiString) a;
    if (it.Value().FindAttribute(TDataStd_AsciiString::GetID(), a))
      ids.push_back(a->Get().ToCString());
  }
  return ids;
}
} // namespace cad
