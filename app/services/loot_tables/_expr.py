"""Safe arithmetic evaluation for wiki {{#expr:}} computed drop rarities.

The wiki renders combined odds like `1/{{#expr:1/(1/23 * 1/37) round 1}}`, folding
several conditional probabilities into one effective rate. Evaluating the expression
yields that mean rate; anything referencing a template variable is not resolvable.
"""

from __future__ import annotations

import ast
import operator
import re

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_EXPR_RE = re.compile(r"\{\{\s*#expr:\s*(.*?)\}\}", re.IGNORECASE | re.DOTALL)
_ROUND_RE = re.compile(r"\bround\b.*$", re.IGNORECASE | re.DOTALL)


def _eval_node(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Div) and right == 0:
            return None
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        operand = _eval_node(node.operand)
        return None if operand is None else _OPS[type(node.op)](operand)
    return None


def safe_eval(expr: str) -> float | None:
    """Evaluate an arithmetic-only expression, or None if it is not pure math."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    return _eval_node(tree.body)


def rarity_from_expr(raw: str) -> tuple[int, int] | None:
    """Resolve a `1/{{#expr:...}}` computed rarity to a (num, denom) pair."""
    match = _EXPR_RE.search(raw)
    if not match:
        return None
    body = _ROUND_RE.sub("", match.group(1)).strip()
    value = safe_eval(body)
    if value is None or value <= 0:
        return None
    before = raw[: match.start()].rstrip()
    if before.endswith("1/"):
        denom = round(value)
    elif value < 1:
        denom = round(1 / value)
    else:
        denom = round(value)
    return (1, denom) if denom >= 1 else None
