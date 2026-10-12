#include "cad/exchange.hpp"
#include "protocol.hpp"
#include <iostream>
int main(int argc, char **argv) {
  if (argc != 2)
    return 2;
  auto r = cad::importStep(argv[1]);
  if (!r) {
    std::cerr << r.error().message;
    return 1;
  }
  auto &shape = r.value().document.features[0].shape;
  std::cout << cad::Json{{"volume", cad::volume(shape)},
                         {"bounds", cad::bounds(shape)},
                         {"losses", r.value().losses}}
                   .dump()
            << "\n";
}
