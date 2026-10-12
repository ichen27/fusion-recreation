#pragma once
#include "document.hpp"
#include <filesystem>
namespace cad {
struct Snapshot {
  Document document;
  std::string journal;
};
enum class SaveFault { None, StopBeforePublish, FailBeforePublish };
Result<void> save(const Document &, const std::filesystem::path &);
Result<Document> load(const std::filesystem::path &);
Result<Snapshot> loadSnapshot(const std::filesystem::path &);
// Internal single-writer interface: callers must hold StoreLock while publishing.
Result<void> publishSnapshot(const Snapshot &, const std::filesystem::path &,
                             SaveFault = SaveFault::None);
class StoreLock {
  int fd_ = -1;

public:
  explicit StoreLock(const std::filesystem::path &);
  ~StoreLock();
  StoreLock(const StoreLock &) = delete;
};
} // namespace cad
