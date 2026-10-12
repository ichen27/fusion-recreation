#pragma once
#include "cad/document.hpp"
#include <nlohmann/json.hpp>
namespace cad {
using Json=nlohmann::json;
Json encode(const Sketch&);
Sketch decodeSketch(const Json&);
Json encode(const Document&);
Document decodeDocument(const Json&);
std::string sha256(const std::string&);
}
