#pragma once
#include "result.hpp"
#include "types.hpp"
#include <array>
#include <memory>
namespace cad {
struct ShapeData;
struct Native;
class Shape {
  std::shared_ptr<ShapeData> data_;
  friend struct Native;

public:
  Shape() = default;
};
Result<Shape> extrude(const Profile &, double depth);
Result<Shape> cutCylinder(const Shape &, const Circle &, double depth);
bool isValid(const Shape &);
double volume(const Shape &);
std::array<double, 6> bounds(const Shape &);
} // namespace cad
