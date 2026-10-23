"""Runs the Pine Script subset that pine.py translates: each expression is evaluated over a whole series of finished
bars at once (value i only uses bars 0..i, so a translated bot never peeks at the future).

Supported: close/open/high/low/volume/hl2/hlc3, numbers, settings, earlier variables, x[k] (k bars ago), + - * /,
comparisons, and/or/not, cond ? a : b, and the functions sma, ema, rma, wma, rsi, highest, lowest, atr, stdev, change, crossover,
crossunder, cross, nz, abs, max, min. None means "not enough history yet".
"""
from __future__ import annotations

import ast
import math
import operator

FUNCS = ("sma", "ema", "rma", "wma", "rsi", "highest", "lowest", "atr", "stdev", "change", "crossover", "crossunder",
         "cross", "nz", "abs", "max", "min")


def _n(x) -> int:
    v = x[-1] if isinstance(x, list) else x
    if v is None:
        raise ValueError("a length must be a fixed number")
    return max(1, int(round(v)))


def _bc(x, n):
    return x if isinstance(x, list) else [x] * n


def _map(f, *series):
    return [None if any(v is None for v in vals) else f(*vals) for vals in zip(*series)]


def _window(s, n, f):
    out = []
    for i in range(len(s)):
        w = s[max(0, i - n + 1):i + 1]
        out.append(f(w) if len(w) == n and None not in w else None)
    return out


def _ema(s, n, alpha=None):
    a, out, prev = alpha or 2 / (n + 1), [], None
    seen = []
    for v in s:
        if v is None:
            out.append(None); continue
        if prev is None:
            seen.append(v)
            if len(seen) == n:
                prev = sum(seen) / n
            out.append(prev); continue
        prev = a * v + (1 - a) * prev
        out.append(prev)
    return out


def _rsi(s, n):
    up = [None] + [None if a is None or b is None else max(b - a, 0.0) for a, b in zip(s, s[1:])]
    dn = [None] + [None if a is None or b is None else max(a - b, 0.0) for a, b in zip(s, s[1:])]
    g, lo = _ema(up, n, 1 / n), _ema(dn, n, 1 / n)
    return [None if x is None or y is None else 100.0 if y == 0 else 100 - 100 / (1 + x / y) for x, y in zip(g, lo)]


def _shift(s, k):
    return [None] * k + s[:len(s) - k] if k else s


def _cross(a, b, up: bool | None):
    out = [None]
    for i in range(1, len(a)):
        p = (a[i - 1], b[i - 1], a[i], b[i])
        if None in p:
            out.append(None); continue
        over, under = p[0] <= p[1] and p[2] > p[3], p[0] >= p[1] and p[2] < p[3]
        out.append(over if up else under if up is False else over or under)
    return out


def call(name: str, args: list, bars: dict, n: int):
    s = lambda i: _bc(args[i], n)  # noqa: E731
    if name in ("sma", "ema", "rma", "wma", "rsi", "highest", "lowest", "stdev") and len(args) == 1:
        args = [bars["high" if name == "highest" else "low" if name == "lowest" else "close"], args[0]]
    if name == "sma":
        return _window(s(0), _n(args[1]), lambda w: sum(w) / len(w))
    if name == "ema":
        return _ema(s(0), _n(args[1]))
    if name == "rma":
        return _ema(s(0), _n(args[1]), 1 / _n(args[1]))
    if name == "wma":
        k = _n(args[1])
        return _window(s(0), k, lambda w: sum(v * (j + 1) for j, v in enumerate(w)) / (k * (k + 1) / 2))
    if name == "rsi":
        return _rsi(s(0), _n(args[1]))
    if name == "highest":
        return _window(s(0), _n(args[1]), max)
    if name == "lowest":
        return _window(s(0), _n(args[1]), min)
    if name == "stdev":
        return _window(s(0), _n(args[1]), lambda w: math.sqrt(sum((v - sum(w) / len(w)) ** 2 for v in w) / len(w)))
    if name == "atr":
        h, lo, c = bars["high"], bars["low"], bars["close"]
        tr = [h[0] - lo[0]] + [max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])) for i in range(1, n)]
        return _ema(tr, _n(args[0]), 1 / _n(args[0]))
    if name == "change":
        k = _n(args[1]) if len(args) > 1 else 1
        return _map(lambda a, b: a - b, s(0), _shift(s(0), k))
    if name in ("crossover", "crossunder", "cross"):
        return _cross(s(0), s(1), True if name == "crossover" else False if name == "crossunder" else None)
    if name == "nz":
        d = args[1] if len(args) > 1 else 0
        return [d if v is None else v for v in s(0)]
    if name == "abs":
        return _map(abs, s(0))
    if name in ("max", "min"):
        f = max if name == "max" else min
        return _map(lambda *v: f(v), *[s(i) for i in range(len(args))])
    raise ValueError(f"unknown function {name}")


_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_CMP = {ast.Gt: operator.gt, ast.Lt: operator.lt, ast.GtE: operator.ge, ast.LtE: operator.le, ast.Eq: operator.eq,
        ast.NotEq: operator.ne}


def evaluate(expr: str, env: dict, n: int):
    """One translated expression over the whole series. env: name -> list (series) or number (setting)."""
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(f"unknown name {node.id}")
            return env[node.id]
        if isinstance(node, ast.UnaryOp):
            v = _bc(ev(node.operand), n)
            if isinstance(node.op, ast.Not):
                return _map(lambda x: not x, v)
            if isinstance(node.op, ast.USub):
                return _map(lambda x: -x, v)
            return v
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            f = _BIN[type(node.op)]
            return _map(lambda a, b: None if isinstance(node.op, ast.Div) and b == 0 else f(a, b),
                        _bc(ev(node.left), n), _bc(ev(node.right), n))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
            return _map(_CMP[type(node.ops[0])], _bc(ev(node.left), n), _bc(ev(node.comparators[0]), n))
        if isinstance(node, ast.BoolOp):
            vals = [_bc(ev(v), n) for v in node.values]
            f = all if isinstance(node.op, ast.And) else any
            return [None if any(v[i] is None for v in vals) else f(bool(v[i]) for v in vals) for i in range(n)]
        if isinstance(node, ast.IfExp):                   # Pine's cond ? a : b, bar by bar
            c, a, b = (_bc(ev(x), n) for x in (node.test, node.body, node.orelse))
            return [None if c[i] is None else a[i] if c[i] else b[i] for i in range(n)]
        if isinstance(node, ast.Subscript):
            k = ev(node.slice)
            return _shift(_bc(ev(node.value), n), _n(k))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
            return call(node.func.id, [ev(a) for a in node.args], env, n)
        raise ValueError(f"can't run: {ast.unparse(node)}")
    return ev(ast.parse(expr, mode="eval"))


def run(series: list[tuple[str, str]], params: dict, bars) -> dict:
    """All translated variables over these bars: {name: list}."""
    n = len(bars)
    env = {"open": [b.o for b in bars], "high": [b.h for b in bars], "low": [b.l for b in bars],
           "close": [b.c for b in bars], "volume": [b.v for b in bars]}
    env["hl2"] = [(b.h + b.l) / 2 for b in bars]
    env["hlc3"] = [(b.h + b.l + b.c) / 3 for b in bars]
    env |= params
    for name, expr in series:
        env[name] = _bc(evaluate(expr, env, n), n)
    return env
