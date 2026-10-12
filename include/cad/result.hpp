#pragma once
#include <optional>
#include <string>
#include <variant>
#include <vector>
namespace cad {
struct Diagnostic { std::string code, message; std::vector<std::string> entityIds; };
template<class T> class Result {
  std::variant<T,Diagnostic> data_;
public:
  Result(T value):data_(std::move(value)) {}
  Result(Diagnostic error):data_(std::move(error)) {}
  explicit operator bool() const {return std::holds_alternative<T>(data_);}
  T& value(){return std::get<T>(data_);}
  const T& value() const{return std::get<T>(data_);}
  const Diagnostic& error() const{return std::get<Diagnostic>(data_);}
};
template<> class Result<void> {
  std::optional<Diagnostic> error_;
public:
  Result()=default;
  Result(Diagnostic error):error_(std::move(error)){}
  explicit operator bool() const{return !error_;}
  const Diagnostic& error() const{return error_.value();}
};
inline Diagnostic fail(std::string code,std::string message,std::vector<std::string> ids={}) {
  return {std::move(code),std::move(message),std::move(ids)};
}
}
