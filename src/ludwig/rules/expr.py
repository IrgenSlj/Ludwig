"""The rule expression language (SPEC section 6): tokenizer, parser and evaluator.

Never passed to Python eval. `and`/`or` evaluate left to right and stop early, so a guard
such as `is_set(x) and x > 3` does not read `x` when it is not set.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

KEYWORDS = {"and", "or", "not", "in", "true", "false"}
FUNCTIONS = {"abs": 1, "min": 2, "max": 2, "is_set": 1}
_COMPARE = {"==", "!=", "<", "<=", ">", ">="}

_TOKEN = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<number>\d+(?:\.\d+)?)
  | (?P<string>"(?:[^"\\]|\\["\\])*")
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
  | (?P<op>==|!=|<=|>=|[<>+\-*/(),\[\]])
    """,
    re.VERBOSE,
)


class ExprError(ValueError):
    """An expression outside the grammar; carries the character position."""

    def __init__(self, message: str, text: str, pos: int):
        super().__init__(f"{message} at column {pos + 1}: {text}")
        self.pos = pos


class UnknownName(KeyError):
    """Raised by a lookup for a name the context does not define."""


@dataclass(frozen=True)
class NotChecked:
    """The result when a value needed by the expression is missing or unusable."""

    reason: str


@dataclass(frozen=True)
class _Tok:
    kind: str
    text: str
    pos: int


def _tokenize(text: str) -> list[_Tok]:
    tokens, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            raise ExprError(f"unexpected character {text[pos]!r}", text, pos)
        kind = m.lastgroup
        if kind != "ws":
            value = m.group()
            if kind == "name" and value in KEYWORDS:
                kind = "kw"
            tokens.append(_Tok(kind, value, pos))
        pos = m.end()
    tokens.append(_Tok("end", "", len(text)))
    return tokens


# Nodes are tuples: ("num", v) ("str", v) ("bool", v) ("name", path) ("neg", x)
# ("not", x) ("bin", op, a, b) ("and", a, b) ("or", a, b) ("in", x, [items]) ("call", f, [args])


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _tokenize(text)
        self.i = 0

    def peek(self) -> _Tok:
        return self.tokens[self.i]

    def take(self, kind: str | None = None, text: str | None = None) -> _Tok:
        tok = self.peek()
        if (kind and tok.kind != kind) or (text and tok.text != text):
            want = text or kind
            got = tok.text or "end of expression"
            raise ExprError(f"expected {want!r}, found {got!r}", self.text, tok.pos)
        self.i += 1
        return tok

    def at(self, text: str) -> bool:
        tok = self.peek()
        return tok.kind in ("op", "kw") and tok.text == text

    def parse(self) -> tuple:
        node = self.or_()
        if self.peek().kind != "end":
            tok = self.peek()
            raise ExprError(f"unexpected {tok.text!r}", self.text, tok.pos)
        return node

    def or_(self) -> tuple:
        node = self.and_()
        while self.at("or"):
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self) -> tuple:
        node = self.not_()
        while self.at("and"):
            self.take()
            node = ("and", node, self.not_())
        return node

    def not_(self) -> tuple:
        if self.at("not"):
            self.take()
            return ("not", self.not_())
        return self.compare()

    def compare(self) -> tuple:
        node = self.sum()
        tok = self.peek()
        if tok.kind == "op" and tok.text in _COMPARE:
            self.take()
            node = ("bin", tok.text, node, self.sum())
        elif self.at("in"):
            self.take()
            self.take("op", "[")
            items = [self.or_()]
            while self.at(","):
                self.take()
                items.append(self.or_())
            self.take("op", "]")
            node = ("in", node, items)
        nxt = self.peek()
        if (nxt.kind == "op" and nxt.text in _COMPARE) or self.at("in"):
            raise ExprError("comparisons cannot be chained", self.text, nxt.pos)
        return node

    def sum(self) -> tuple:
        node = self.product()
        while self.at("+") or self.at("-"):
            op = self.take().text
            node = ("bin", op, node, self.product())
        return node

    def product(self) -> tuple:
        node = self.unary()
        while self.at("*") or self.at("/"):
            op = self.take().text
            node = ("bin", op, node, self.unary())
        return node

    def unary(self) -> tuple:
        if self.at("-"):
            self.take()
            return ("neg", self.unary())
        return self.atom()

    def atom(self) -> tuple:
        tok = self.peek()
        if tok.kind == "number":
            self.take()
            return ("num", float(tok.text))
        if tok.kind == "string":
            self.take()
            return ("str", re.sub(r"\\([\"\\])", r"\1", tok.text[1:-1]))
        if tok.kind == "kw" and tok.text in ("true", "false"):
            self.take()
            return ("bool", tok.text == "true")
        if tok.kind == "name":
            self.take()
            if self.at("("):
                if tok.text not in FUNCTIONS:
                    raise ExprError(f"unknown function {tok.text!r}", self.text, tok.pos)
                self.take()
                args = [self.or_()]
                while self.at(","):
                    self.take()
                    args.append(self.or_())
                self.take("op", ")")
                if len(args) != FUNCTIONS[tok.text]:
                    n = FUNCTIONS[tok.text]
                    raise ExprError(f"{tok.text}() takes {n} argument(s)", self.text, tok.pos)
                if tok.text == "is_set" and args[0][0] != "name":
                    raise ExprError("is_set() takes a name", self.text, tok.pos)
                return ("call", tok.text, args)
            return ("name", tok.text)
        if self.at("("):
            self.take()
            node = self.or_()
            self.take("op", ")")
            return node
        raise ExprError(f"unexpected {tok.text or 'end of expression'!r}", self.text, tok.pos)


def _names(node: tuple, out: set[str]) -> None:
    if node[0] == "name":
        out.add(node[1])
    for part in node[1:]:
        if isinstance(part, tuple):
            _names(part, out)
        elif isinstance(part, list):
            for item in part:
                _names(item, out)


@dataclass
class Result:
    """The value of an expression (or NotChecked) and the names it read, in order."""

    value: Any
    used: list[str] = field(default_factory=list)


def _kind(v: Any) -> str:
    if isinstance(v, bool):
        return "true/false"
    if isinstance(v, int | float):
        return "number"
    if isinstance(v, str):
        return "text"
    return type(v).__name__


class _Stop(Exception):
    def __init__(self, nc: NotChecked):
        self.nc = nc


@dataclass(frozen=True)
class Expr:
    """A parsed expression. Build with `compile_expr`."""

    text: str
    tree: tuple
    names: frozenset[str]

    def evaluate(self, lookup: Callable[[str], Any]) -> Result:
        """Evaluate against `lookup(name)`; a None value makes the result NotChecked."""
        used: list[str] = []
        try:
            value = self._eval(self.tree, lookup, used)
        except _Stop as stop:
            return Result(stop.nc, used)
        return Result(value, used)

    def _eval(self, node: tuple, lookup: Callable[[str], Any], used: list[str]) -> Any:
        op = node[0]
        if op in ("num", "str", "bool"):
            return node[1]
        if op == "name":
            if node[1] not in used:
                used.append(node[1])
            value = lookup(node[1])
            if value is None:
                raise _Stop(NotChecked(f"{node[1]} is not set"))
            return value
        if op == "call" and node[1] == "is_set":
            name = node[2][0][1]
            if name not in used:
                used.append(name)
            return lookup(name) is not None
        if op == "and":
            left = self._bool(self._eval(node[1], lookup, used), "and")
            return left and self._bool(self._eval(node[2], lookup, used), "and")
        if op == "or":
            left = self._bool(self._eval(node[1], lookup, used), "or")
            return left or self._bool(self._eval(node[2], lookup, used), "or")
        if op == "not":
            return not self._bool(self._eval(node[1], lookup, used), "not")
        if op == "neg":
            return -self._num(self._eval(node[1], lookup, used), "-")
        if op == "in":
            value = self._eval(node[1], lookup, used)
            items = [self._eval(item, lookup, used) for item in node[2]]
            return any(_kind(value) == _kind(item) and value == item for item in items)
        if op == "call":
            args = [self._num(self._eval(a, lookup, used), node[1]) for a in node[2]]
            return {"abs": abs, "min": min, "max": max}[node[1]](*args)
        if op == "bin":
            return self._binary(
                node[1], self._eval(node[2], lookup, used), self._eval(node[3], lookup, used)
            )
        raise AssertionError(op)

    def _bool(self, v: Any, where: str) -> bool:
        if not isinstance(v, bool):
            raise _Stop(NotChecked(f"'{where}' needs true/false, got {_kind(v)} {v!r}"))
        return v

    def _num(self, v: Any, where: str) -> float:
        if _kind(v) != "number":
            raise _Stop(NotChecked(f"'{where}' needs a number, got {_kind(v)} {v!r}"))
        return v

    def _binary(self, op: str, a: Any, b: Any) -> Any:
        if op in ("==", "!="):
            if _kind(a) != _kind(b):
                raise _Stop(NotChecked(f"cannot compare {_kind(a)} {a!r} with {_kind(b)} {b!r}"))
            return (a == b) if op == "==" else (a != b)
        if op in ("<", "<=", ">", ">="):
            if _kind(a) != _kind(b) or _kind(a) == "true/false":
                raise _Stop(NotChecked(f"cannot compare {_kind(a)} {a!r} with {_kind(b)} {b!r}"))
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        a, b = self._num(a, op), self._num(b, op)
        if op == "/" and b == 0:
            raise _Stop(NotChecked("division by zero"))
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        return a * b if op == "*" else a / b


def compile_expr(text: str) -> Expr:
    """Parse an expression; raises ExprError for anything outside the grammar."""
    if not isinstance(text, str) or not text.strip():
        raise ExprError("empty expression", str(text), 0)
    tree = _Parser(text).parse()
    names: set[str] = set()
    _names(tree, names)
    return Expr(text, tree, frozenset(names))
