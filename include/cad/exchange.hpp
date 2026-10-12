#pragma once
#include "document.hpp"
#include <filesystem>
namespace cad {
struct ImportResult {
  Document document;
  std::vector<std::string> losses;
};
Result<void> exportStep(const Document &, const std::filesystem::path &);
Result<ImportResult> importStep(const std::filesystem::path &);
} // namespace cad
