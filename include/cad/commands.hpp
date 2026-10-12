#pragma once
#include "storage.hpp"
namespace cad {
enum class Operation {CreateSketch,Extrude,Hole,EditSketch,Undo,Redo};
struct SketchCommand {Id featureId;Sketch sketch;};
struct ExtrudeCommand {Id featureId;ExtrudeParams parameters;};
struct HoleCommand {Id featureId;HoleParams parameters;};
using CommandParameters=std::variant<std::monostate,SketchCommand,ExtrudeCommand,HoleCommand>;
struct Command {Id documentId;Revision expectedRevision;Id transactionId;Operation operation;CommandParameters parameters;};
struct Reply {Revision committedRevision;std::vector<Id> affectedFeatureIds;std::vector<Diagnostic> diagnostics;};
struct Evaluation {Snapshot snapshot;Reply reply;};
Result<Evaluation> evaluate(const Snapshot&,const Command&);
class CommandStore {
 std::filesystem::path path_;
public:
 CommandStore(std::filesystem::path path,Id documentId);
 Result<Reply> apply(const Command&);
 Result<Snapshot> snapshot() const;
};
}
