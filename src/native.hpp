#pragma once
#include "cad/kernel.hpp"
#include <TopoDS_Shape.hxx>
#include <stdexcept>
namespace cad {
struct ShapeData {TopoDS_Shape shape;};
struct Native {
 static const TopoDS_Shape& get(const Shape& s){if(!s.data_) throw std::runtime_error("Empty shape");return s.data_->shape;}
 static Shape wrap(const TopoDS_Shape& s){Shape out;out.data_=std::make_shared<ShapeData>(ShapeData{s});return out;}
};
}
