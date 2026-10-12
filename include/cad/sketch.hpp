#pragma once
#include "result.hpp"
#include "types.hpp"
#include <variant>
namespace cad {
struct Line {
  Id id;
  Point2 a, b;
  bool construction = false;
};
struct Arc {
  Id id;
  Point2 center;
  double radius, startAngle, endAngle;
  bool construction = false;
};
struct CircleEntity {
  Id id;
  Point2 center;
  double radius;
  bool construction = false;
};
using Entity = std::variant<Line, Arc, CircleEntity>;
enum class ConstraintKind { Coincident, Horizontal, Vertical, Distance, Radius, FixedPoint };
struct Constraint {
  Id id;
  ConstraintKind kind;
  std::vector<Id> entityIds;
  double value = 0;
};
struct Sketch {
  std::vector<Entity> entities;
  std::vector<Constraint> constraints;
};
struct SketchSolution {
  Profile profile;
  std::vector<Circle> circles;
  int degreesOfFreedom = 0;
  std::vector<Id> conflictingIds, redundantIds;
  double maxResidual = 0;
};
Result<SketchSolution> solve(const Sketch &);
} // namespace cad
