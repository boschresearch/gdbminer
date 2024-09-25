// This source code is from 
//  https://github.com/rollbear/variant_parse/tree/master
// This source code is under Public Domain

#include <fcntl.h>
#include <unistd.h>
#include <iostream>
#include <string>
#include <memory>
#include <map>
#include <variant>
#include <optional>
#include <string_view>
#include <utility>


template <typename ... F>
class overload : private F...
{
public:
  overload(F... f) : F(f)... {}
  using F::operator()...;
};



template <char>
struct C        {};

struct number   { double           value; };
struct eof      {};

using token = std::variant<
  number,
  C<'-'>,
  C<'+'>,
  C<'/'>,
  C<'*'>,
  C<'('>,
  C<')'>,
  eof
>;

class lex
{
public:
  lex(std::string_view  s);
  token next_token();
  token peek();
  void drop();
private:
  token scan_token();
  token scan_number();

  std::string_view  buffer;
  const char* iter;
  const char* end;
  std::optional<token> lookahead;
};

class calculator
{
public:
  double parse(std::string_view  s);

private:
  using variable_store = std::map<std::string_view , double, std::less<>>;

  double parse_expr();
  double parse_factor();
  double parse_term();
  double parse_paren();


  std::unique_ptr<lex> lexer;
  variable_store       memory;
};


lex::lex(std::string_view  s)
  : buffer{std::move(s)}
  , iter{buffer.begin()}
  , end{iter + buffer.length()}
{
}

token lex::next_token()
{
  if (lookahead)
  {
    auto t = std::move(*lookahead);
    drop();
    return t;
  }
  return scan_token();
}

token lex::scan_token()
{
  for (;;)
  {
  if (iter == end) return {eof{}};
    if (*iter != ' ' && *iter != '\t' && *iter != '\n')
      break;
    ++iter;
  }

  switch (*iter)
  {
    case '(': ++iter;return {C<'('>{}};
    case ')': ++iter;return {C<')'>{}};
    case '/': ++iter;return {C<'/'>{}};
    case '*': ++iter;return {C<'*'>{}};
    case '+': ++iter;return {C<'+'>{}};
    case '-': ++iter;return {C<'-'>{}};
    case '0': case '1': case '2': case '3': case '4':
    case '5': case '6': case '7': case '8': case '9': //case '.':
      return scan_number();
  }
  throw "unknown";
}

token lex::scan_number()
{
  char* number_end;

  number rv;
  rv.value = std::strtod(iter, &number_end);
  iter = number_end;
  return {rv};
}

token lex::peek()
{
  if (!lookahead)
  {
    lookahead = scan_token();
  }
  return *lookahead;
}

void lex::drop()
{
  lookahead = std::nullopt;
}


double calculator::parse(std::string_view  s)
{
  lexer = std::make_unique<lex>(std::move(s));
  auto t  = lexer->peek();
  auto rv = std::visit(
    overload{
      [&](auto)     { return parse_expr();}
    },
    t);
  if (!std::holds_alternative<eof>(lexer->next_token())) throw "garbage after expr";
  return rv;
}

double calculator::parse_expr()
{
  auto v = parse_term();
  for (bool done = false; !done;)
  {
    auto t = lexer->peek();
    v = std::visit(
      overload{
        [&](C<'+'>) { lexer->drop(); return v + parse_term(); },
        [&](C<'-'>) { lexer->drop(); return v - parse_term(); },
        [&](auto)   { done = true; return v; }
      },
      t);
  }
  return v;
}

double calculator::parse_factor()
{
  auto t = lexer->next_token();
  return std::visit(
    overload{
      //[=](ident var)      { return lookup(var.value); },
      [=](number n)       { return n.value; },
      // [=](C<'+'>)         { return parse_term(); },
      // [=](C<'-'>)         { return -parse_term(); },
      [=](C<'('>)         { return parse_paren(); },
      [=](auto) -> double { throw "unexpected"; }
    },
    t);
}

double calculator::parse_term()
{
  auto v = parse_factor();
  for (bool done = false; !done;)
  {
    auto t = lexer->peek();
    v = std::visit(
      overload{
        [&](C<'/'>) { lexer->drop(); return v / parse_factor(); },
        [&](C<'*'>) { lexer->drop(); return v * parse_factor(); },
        [&](auto)   { done = true; return v; }
      },
      t);
  }
  return v;
}

double calculator::parse_paren()
{
  auto v = parse_expr();
  auto t = lexer->next_token();
  if (!std::holds_alternative<C<')'>>(t))
  {
    throw "expected ')'";
  }
  return v;
}


char my_string[10240];

calculator c;

int main(int argc, char *argv[]) {

  int ret = -1;
  if (argc == 1) {
    int chars = read(fileno(stdin), my_string, 10239);
    if (chars <= 0) {
      exit(1);
    }
    my_string[chars] = 0;
    /*char *v = fgets(my_string, 10240, stdin);
    if (!v) {
      exit(1);
    }*/
    /*strip_input(my_string);*/
  } else {
    int fd = open(argv[1], O_RDONLY);
    int chars = read(fd, my_string, 10240);
    if (!chars) {
      exit(3);
    }
    my_string[chars] = 0;
    /*chars = strip_input(my_string);
    if (!chars) {
      exit(4);
    }*/
    close(fd);
  }
  printf("val: <%s>\n", my_string);


  std::string_view str(my_string);

  try {
      std::cout << c.parse(std::move(str)) << '\n';
  }
  catch (const char* m)
  {
      std::cout << "oops: " << m << '\n';
      exit(1);
  }


}
