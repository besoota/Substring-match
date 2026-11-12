"""Public interface for the ONFA regular-expression matcher."""

from .engine import (
    Context,
    Direction,
    Eval,
    build_ast,
    evaluate_ast,
    substring_match,
)

__all__ = [
    "Context",
    "Direction",
    "Eval",
    "build_ast",
    "evaluate_ast",
    "substring_match",
]

