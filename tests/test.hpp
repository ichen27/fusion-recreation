#pragma once
#include <cmath>
#include <iostream>
#include <stdexcept>
#define CHECK(x)                                                                                   \
  do {                                                                                             \
    if (!(x))                                                                                      \
      throw std::runtime_error(std::string(__FILE__) + ":" + std::to_string(__LINE__) + ": " +     \
                               #x);                                                                \
  } while (false)
inline bool near(double a, double b) {
  return std::abs(a - b) <= std::max(1e-6, std::abs(b) * 1e-8);
}
