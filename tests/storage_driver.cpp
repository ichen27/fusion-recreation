#include "cad/storage.hpp"
#include "document_fixtures.hpp"
#include <iostream>
int main(int argc, char **argv) {
  using namespace cad;
  if (argc != 3)
    return 2;
  std::string mode = argv[1];
  auto path = std::filesystem::path(argv[2]);
  if (mode == "read") {
    auto r = load(path);
    if (!r)
      return 1;
    std::cout << r.value().revision;
    return 0;
  }
  auto d = recompute(fixtureDocument());
  if (!d)
    return 1;
  d.value().revision = mode == "initial" ? 1 : 2;
  StoreLock lock(path);
  auto fault = mode == "stop"   ? SaveFault::StopBeforePublish
               : mode == "fail" ? SaveFault::FailBeforePublish
                                : SaveFault::None;
  if (mode == "after")
    fault = SaveFault::FailAfterPublish;
  auto r = publishSnapshot({d.value(), ""}, path, fault);
  if (!r)
    std::cerr << r.error().code << "\n";
  return r ? 0 : 1;
}
