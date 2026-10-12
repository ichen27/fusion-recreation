#include "cad/commands.hpp"
#include "protocol.hpp"
#include <set>
namespace cad {
Result<Evaluation> evaluate(const Snapshot &initial, const Command &c) {
  try {
    if (c.documentId != initial.document.id)
      return fail("DocumentMismatch", "Command targets a different document");
    if (c.transactionId.empty() || c.transactionId.size() > 256)
      return fail("InvalidTransaction", "Transaction ID must contain 1..256 bytes");
    Json journal = initial.journal.empty() ? Json{{"transactions", Json::object()},
                                                  {"past", Json::array()},
                                                  {"future", Json::array()}}
                                           : Json::parse(initial.journal);
    auto hash = sha256(encode(c).dump());
    auto &transactions = journal.at("transactions");
    if (transactions.contains(c.transactionId)) {
      auto &prior = transactions.at(c.transactionId);
      if (prior.at("hash") != hash)
        return fail("TransactionConflict", "Transaction ID was already used for another command",
                    {c.transactionId});
      const auto &reply = prior.at("reply");
      return Evaluation{initial,
                        {reply.at("revision").get<Revision>(),
                         reply.at("affectedFeatureIds").get<std::vector<Id>>(),
                         {}}};
    }
    if (c.expectedRevision != initial.document.revision)
      return fail("RevisionConflict", "Expected revision does not match current revision");
    Document edited = initial.document;
    std::vector<Id> changed;
    auto &past = journal.at("past");
    auto &future = journal.at("future");
    if (c.operation == Operation::Undo || c.operation == Operation::Redo) {
      if (!std::holds_alternative<std::monostate>(c.parameters))
        return fail("InvalidCommand", "Undo/Redo require empty parameters");
      auto &from = c.operation == Operation::Undo ? past : future;
      auto &to = c.operation == Operation::Undo ? future : past;
      if (from.empty())
        return fail(c.operation == Operation::Undo ? "NothingToUndo" : "NothingToRedo",
                    "No corresponding history state");
      edited = decodeDocument(from.back());
      from.erase(from.size() - 1);
      to.push_back(encode(initial.document));
      for (auto &f : initial.document.features)
        changed.push_back(f.id);
      for (auto &f : edited.features)
        if (std::find(changed.begin(), changed.end(), f.id) == changed.end())
          changed.push_back(f.id);
    } else {
      Id id;
      if (c.operation == Operation::CreateSketch || c.operation == Operation::EditSketch) {
        auto p = std::get<SketchCommand>(c.parameters);
        id = p.featureId;
        if (c.operation == Operation::CreateSketch)
          edited.features.push_back({id, FeatureKind::Sketch, {}, p.sketch});
        else {
          auto it = std::find_if(edited.features.begin(), edited.features.end(),
                                 [&](const auto &f) { return f.id == id; });
          if (it == edited.features.end() || it->kind != FeatureKind::Sketch)
            return fail("BrokenReference", "Edit target is not a sketch", {id});
          it->parameters = p.sketch;
        }
      } else if (c.operation == Operation::Extrude) {
        auto p = std::get<ExtrudeCommand>(c.parameters);
        id = p.featureId;
        edited.features.push_back(
            {id, FeatureKind::Extrude, {p.parameters.profileId}, p.parameters});
      } else if (c.operation == Operation::Hole) {
        auto p = std::get<HoleCommand>(c.parameters);
        id = p.featureId;
        edited.features.push_back(
            {id, FeatureKind::Hole, {p.parameters.baseFeatureId}, p.parameters});
      } else
        return fail("InvalidCommand", "Unsupported operation");
      if (id.empty() || id.size() > 256)
        return fail("InvalidId", "Feature ID must contain 1..256 bytes");
      changed.push_back(id);
      std::set<Id> affected{id};
      bool more = true;
      while (more) {
        more = false;
        for (auto &f : edited.features)
          for (auto &dep : f.inputIds)
            if (affected.contains(dep) && affected.insert(f.id).second) {
              changed.push_back(f.id);
              more = true;
            }
      }
      past.push_back(encode(initial.document));
      future = Json::array();
    }
    // One OCAF label transaction and a complete application snapshot per command.
    DocumentSession session(initial.document);
    auto b = session.begin();
    if (!b)
      return b.error();
    auto replace = session.replace(edited);
    if (!replace)
      return replace.error();
    auto commit = session.commit();
    if (!commit)
      return commit.error();
    Reply reply{session.current().revision, changed, {}};
    transactions[c.transactionId] = {{"hash", hash}, {"reply", encode(reply)}};
    return Evaluation{{session.current(), journal.dump()}, reply};
  } catch (const std::exception &e) {
    return fail("InvalidCommand", e.what());
  }
}
CommandStore::CommandStore(std::filesystem::path path, Id documentId) : path_(std::move(path)) {
  StoreLock lock(path_);
  if (!std::filesystem::exists(path_ / "current.json")) {
    auto r = publishSnapshot({Document{documentId, Units::Millimeter, 0, {}}, ""}, path_);
    if (!r)
      throw std::runtime_error(r.error().message);
  } else {
    auto r = loadSnapshot(path_);
    if (!r)
      throw std::runtime_error(r.error().code + ": " + r.error().message);
    if (r.value().document.id != documentId)
      throw std::runtime_error("DocumentMismatch: store belongs to another document");
  }
}
Result<Snapshot> CommandStore::snapshot() const {
  return loadSnapshot(path_);
}
Result<Reply> CommandStore::apply(const Command &c, SaveFault fault) {
  try {
    StoreLock lock(path_);
    auto initial = loadSnapshot(path_);
    if (!initial)
      return initial.error();
    auto next = evaluate(initial.value(), c);
    if (!next)
      return next.error();
    if (next.value().snapshot.document.revision != initial.value().document.revision) {
      auto written = publishSnapshot(next.value().snapshot, path_, fault);
      if (!written)
        return written.error();
    } else {
      auto confirmed = confirmDurability(path_, fault == SaveFault::FailAfterPublish);
      if (!confirmed)
        return confirmed.error();
    }
    return next.value().reply;
  } catch (const std::exception &e) {
    return fail("StorageFailure", e.what());
  }
}
} // namespace cad
