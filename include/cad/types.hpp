#pragma once
#include <cstdint>
#include <string>
#include <vector>
namespace cad {
using Id=std::string;
using Revision=std::uint64_t;
enum class Units {Millimeter,Inch};
struct Point2 {double x{},y{}; bool operator==(const Point2&) const=default;};
struct Profile {std::vector<Point2> vertices; bool closed=false;};
struct Circle {Point2 center; double radius{};};
struct Dimensions {double width{},height{},depth{};};
}
