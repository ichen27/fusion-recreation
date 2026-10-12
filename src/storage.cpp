#include "cad/storage.hpp"
#include "codec.hpp"
#include <cerrno>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <sys/file.h>
#include <unistd.h>
namespace cad {
namespace fs = std::filesystem;
namespace {
constexpr size_t maxBytes = 64 * 1024 * 1024;
std::string read(const fs::path &p) {
  if (fs::file_size(p) > maxBytes)
    throw std::runtime_error("File exceeds 64 MiB limit");
  std::ifstream f(p, std::ios::binary);
  if (!f)
    throw std::runtime_error("Cannot open " + p.string());
  return std::string(std::istreambuf_iterator<char>(f), {});
}
void writeSync(const fs::path &path, const std::string &text) {
  int fd = open(path.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0)
    throw std::runtime_error(std::strerror(errno));
  size_t offset = 0;
  while (offset < text.size()) {
    auto n = write(fd, text.data() + offset, text.size() - offset);
    if (n < 0 && errno == EINTR)
      continue;
    if (n <= 0) {
      close(fd);
      throw std::runtime_error("Write failed");
    }
    offset += size_t(n);
  }
  if (fsync(fd) < 0) {
    close(fd);
    throw std::runtime_error("File sync failed");
  }
  close(fd);
}
void syncDir(const fs::path &p) {
  int fd = open(p.c_str(), O_RDONLY);
  if (fd < 0)
    throw std::runtime_error("Directory open failed");
  int r = fsync(fd);
  close(fd);
  if (r < 0)
    throw std::runtime_error("Directory sync failed");
}
} // namespace
StoreLock::StoreLock(const fs::path &path) {
  fs::create_directories(path);
  fd_ = open((path / ".writer.lock").c_str(), O_RDWR | O_CREAT, 0600);
  if (fd_ < 0)
    throw std::runtime_error("Cannot open writer lock");
  while (flock(fd_, LOCK_EX) < 0) {
    if (errno == EINTR)
      continue;
    close(fd_);
    fd_ = -1;
    throw std::runtime_error("Cannot acquire writer lock");
  }
}
StoreLock::~StoreLock() {
  if (fd_ >= 0) {
    flock(fd_, LOCK_UN);
    close(fd_);
  }
}
Result<void> publishSnapshot(const Snapshot &snapshot, const fs::path &path, SaveFault fault) {
  bool published = false;
  try {
    auto validated = recompute(snapshot.document);
    if (!validated)
      return validated.error();
    Json state = {{"schema", 1},
                  {"engine", "OCCT-8.0.1"},
                  {"document", encode(validated.value())},
                  {"journal", snapshot.journal}};
    auto payload = state.dump();
    if (payload.size() > maxBytes)
      return fail("StorageLimit", "Document exceeds 64 MiB");
    auto hash = sha256(payload);
    fs::create_directories(path / "revisions");
    auto revision = path / "revisions" / hash;
    if (!fs::exists(revision)) {
      auto staging = path / "revisions" / (".tmp-" + std::to_string(getpid()));
      fs::create_directories(staging);
      writeSync(staging / "state.json", payload);
      syncDir(staging);
      fs::rename(staging, revision);
      syncDir(path / "revisions");
    } else if (sha256(read(revision / "state.json")) != hash)
      return fail("ChecksumMismatch", "Existing immutable payload is corrupt");
    if (fault == SaveFault::StopBeforePublish) {
      writeSync(path / "fault-ready", "ready");
      raise(SIGSTOP);
    }
    if (fault == SaveFault::FailBeforePublish) {
      // Force a real failing write-open against a directory before publication.
      writeSync(revision, "fault");
      return fail("StorageFailure", "Fault injection unexpectedly allowed a directory write");
    }
    auto manifest = Json{{"schema", 1}, {"payload", hash}, {"sha256", hash}}.dump();
    auto temp = path / (".current-" + std::to_string(getpid()));
    writeSync(temp, manifest);
    fs::rename(temp, path / "current.json");
    published = true;
    if (fault == SaveFault::FailAfterPublish)
      writeSync(revision, "fault after publication");
    syncDir(path);
    return {};
  } catch (const std::exception &e) {
    return fail(published ? "CommitUncertain" : "StorageFailure",
                published ? std::string("Manifest published but durability could not be confirmed; "
                                        "reopen or retry the same transaction: ") +
                                e.what()
                          : e.what());
  }
}
Result<void> save(const Document &d, const fs::path &path) {
  try {
    StoreLock lock(path);
    if (fs::exists(path / "current.json")) {
      auto existing = loadSnapshot(path);
      if (!existing)
        return existing.error();
      if (!existing.value().journal.empty()) {
        if (encode(d) != encode(existing.value().document))
          return fail("ManagedDocument",
                      "Use CommandStore to edit a document with transaction history");
        return {};
      }
    }
    return publishSnapshot({d, ""}, path);
  } catch (const std::exception &e) {
    return fail("StorageFailure", e.what());
  }
}
Result<Snapshot> loadSnapshot(const fs::path &path) {
  try {
    auto manifest = Json::parse(read(path / "current.json"));
    if (manifest.at("schema") != 1)
      return fail("UnsupportedSchema", "Unsupported manifest schema");
    auto hash = manifest.at("payload").get<std::string>();
    if (hash.size() != 64 || hash.find_first_not_of("0123456789abcdef") != std::string::npos)
      return fail("InvalidManifest", "Invalid payload identifier");
    auto payload = read(path / "revisions" / hash / "state.json");
    if (sha256(payload) != manifest.at("sha256").get<std::string>() || sha256(payload) != hash)
      return fail("ChecksumMismatch", "Payload checksum does not match manifest");
    auto state = Json::parse(payload);
    if (state.at("schema") != 1)
      return fail("UnsupportedSchema", "Unsupported document schema");
    if (state.at("engine") != "OCCT-8.0.1")
      return fail("UnsupportedEngine", "Native BREP engine version requires migration");
    auto doc = recompute(decodeDocument(state.at("document")));
    if (!doc)
      return doc.error();
    return Snapshot{std::move(doc.value()), state.at("journal").get<std::string>()};
  } catch (const std::exception &e) {
    return fail("StorageFailure", e.what());
  }
}
Result<Document> load(const fs::path &p) {
  auto r = loadSnapshot(p);
  if (!r)
    return r.error();
  return r.value().document;
}
} // namespace cad
