#pragma once
#include "kernel.hpp"
#include "sketch.hpp"
#include "selection.hpp"
#include <map>
#include <memory>
namespace cad {
enum class FeatureKind {Sketch,Extrude,Hole,ImportedBody};
enum class FeatureStatus {Pending,Valid};
enum class CenterMode {BodyCenter};
struct ExtrudeParams {Id profileId;double depth;};
struct HoleParams {Id baseFeatureId;Selection support;double radius;CenterMode centerMode=CenterMode::BodyCenter;};
struct ImportedBodyParams {Id payloadId;};
using Parameters=std::variant<Sketch,ExtrudeParams,HoleParams,ImportedBodyParams>;
struct Feature {
 Id id;FeatureKind kind;std::vector<Id> inputIds;Parameters parameters;
 FeatureStatus status=FeatureStatus::Pending;
 Shape shape;SketchSolution sketch;
 std::map<std::string,std::vector<Id>> topology;
};
struct Document {Id id;Units units=Units::Millimeter;Revision revision=0;std::vector<Feature> features;};
Result<Document> recompute(const Document&,const std::vector<Id>& changed={});
const Feature* findFeature(const Document&,const Id&);
class DocumentSession {
 struct Impl;std::unique_ptr<Impl> impl_;
public:
 explicit DocumentSession(Document);
 ~DocumentSession();
 DocumentSession(const DocumentSession&)=delete;
 Result<void> begin();
 Result<void> replace(Document);
 Result<void> commit();
 void abort();
 Result<void> undo();
 Result<void> redo();
 const Document& current() const;
 std::vector<Id> persistedFeatureIds() const;
};
}
