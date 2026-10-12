#include "cad/storage.hpp"
#include "codec.hpp"
#include "document_fixtures.hpp"
#include "test.hpp"
#include <fstream>
#include <unistd.h>
int main() {
  using namespace cad;
  namespace fs = std::filesystem;
  auto path = fs::temp_directory_path() / ("cad-storage-" + std::to_string(getpid()));
  fs::remove_all(path);
  CHECK(sha256("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  CHECK(sha256("") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  auto d = recompute(fixtureDocument());
  CHECK(d);
  d.value().units = Units::Inch;
  d.value().revision = 7;
  CHECK(save(d.value(), path));
  auto r = load(path);
  CHECK(r);
  CHECK(r.value().id == d.value().id);
  CHECK(r.value().units == Units::Inch);
  CHECK(r.value().revision == 7);
  CHECK(near(volume(r.value().features[2].shape), volume(d.value().features[2].shape)));
  CHECK(std::get<Sketch>(r.value().features[0].parameters).constraints.back().value == 20);
  std::ofstream(path / "current.json") << "{\"schema\":999}";
  auto future = load(path);
  CHECK(!future);
  CHECK(future.error().code == "UnsupportedSchema");
  fs::remove(path / "current.json");
  CHECK(save(d.value(), path));
  for (auto &dir : fs::directory_iterator(path / "revisions"))
    std::ofstream(dir.path() / "state.json") << "truncated";
  auto corrupt = load(path);
  CHECK(!corrupt);
  CHECK(corrupt.error().code == "ChecksumMismatch");
  fs::remove_all(path);
}
