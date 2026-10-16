import ast
import operator

_OPERATORS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calculate(expression: str) -> dict:
    """Evaluate ordinary arithmetic only; no names, calls, attributes, or code execution."""
    def visit(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 12:
                raise ValueError("Exponent is too large")
            return _OPERATORS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
            return _OPERATORS[type(node.op)](visit(node.operand))
        raise ValueError("Only arithmetic expressions are supported")

    cleaned = expression.replace("×", "*").replace("÷", "/").replace("^", "**")
    try:
        result = visit(ast.parse(cleaned, mode="eval").body)
        return {"expression": expression, "result": result}
    except (SyntaxError, ValueError, ZeroDivisionError, TypeError) as exc:
        return {"expression": expression, "error": str(exc)}
