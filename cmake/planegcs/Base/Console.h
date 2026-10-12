#pragma once
#include <cstdarg>
#include <cstdio>
namespace Base {
struct ConsoleAdapter {
  void log(const char *format, ...) {
    va_list a;
    va_start(a, format);
    std::vfprintf(stderr, format, a);
    va_end(a);
  }
  void warning(const char *format, ...) {
    va_list a;
    va_start(a, format);
    std::vfprintf(stderr, format, a);
    va_end(a);
  }
};
inline ConsoleAdapter &Console() {
  static ConsoleAdapter c;
  return c;
}
} // namespace Base
