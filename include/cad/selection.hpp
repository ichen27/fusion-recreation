#pragma once
#include "result.hpp"
#include "types.hpp"
namespace cad {
struct Document;
struct Selection {Id featureId;std::string semanticRole;std::vector<Id> evolutionIds;};
Result<Id> resolve(const Document&,const Selection&);
}
