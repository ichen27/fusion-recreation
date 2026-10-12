#pragma once
#include "cad/commands.hpp"
#include "codec.hpp"
namespace cad {
Json encode(const Command&);
Command decodeCommand(const Json&);
Json encode(const Reply&);
Json errorReply(const Diagnostic&);
}
