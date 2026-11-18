"""Regular-expression parser and ONFA substring matcher.

This module is separated from the benchmark so that the experiment measures
the matcher without Jupyter's cell state or plotting overhead.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import Literal, TypeAlias

from lark import Lark, Transformer, v_args


REGEX_GRAMMAR = r"""
?start: alternation

?alternation: alternation "|" concatenation -> make_or
            | concatenation

?concatenation: concatenation repetition -> make_seq
              | repetition

?repetition: repetition "*" -> make_star
           | atom

?atom: "(?=" alternation ")" -> positive_lookahead
     | "(?<=" alternation ")" -> positive_lookbehind
     | "(?!" alternation ")" -> negative_lookahead
     | "(?<!" alternation ")" -> negative_lookbehind
     | "(" alternation ")" -> group
     | "∅" -> empty_set
     | "ε" -> epsilon
     | "." -> wildcard
     | ESCAPED -> escaped
     | LITERAL -> literal

ESCAPED: /\\[^\n]/
LITERAL: /[^|*().\\∅ε]/
"""


class AstNode:
    """Base class for regular-expression AST nodes."""


@dataclass(frozen=True)
class OrAstNode(AstNode):
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class SeqAstNode(AstNode):
    left: AstNode
    right: AstNode


@dataclass(frozen=True)
class StarAstNode(AstNode):
    left: AstNode


@dataclass(frozen=True)
class LiteralCharacterAstNode(AstNode):
    char: str


@dataclass(frozen=True)
class WildcardAstNode(AstNode):
    """Match any single input character."""


@dataclass(frozen=True)
class EmptySetAstNode(AstNode):
    pass


@dataclass(frozen=True)
class EpsilonAstNode(AstNode):
    pass


@dataclass(frozen=True)
class PositiveLookaheadAstNode(AstNode):
    left: AstNode


@dataclass(frozen=True)
class PositiveLookbehindAstNode(AstNode):
    left: AstNode


@dataclass(frozen=True)
class NegativeLookaheadAstNode(AstNode):
    left: AstNode


@dataclass(frozen=True)
class NegativeLookbehindAstNode(AstNode):
    left: AstNode


class OraclePolarity(Enum):
    POSITIVE = auto()
    NEGATIVE = auto()


@dataclass(frozen=True)
class OracleAstNode(AstNode):
    oracle_id: int
    pole: OraclePolarity


@v_args(inline=True)
class RegexAstTransformer(Transformer):
    def make_or(self, left: AstNode, right: AstNode) -> AstNode:
        return OrAstNode(left, right)

    def make_seq(self, left: AstNode, right: AstNode) -> AstNode:
        return SeqAstNode(left, right)

    def make_star(self, left: AstNode) -> AstNode:
        return StarAstNode(left)

    def group(self, left: AstNode) -> AstNode:
        return left

    def literal(self, token) -> AstNode:
        return LiteralCharacterAstNode(str(token))

    def escaped(self, token) -> AstNode:
        return LiteralCharacterAstNode(str(token)[1])

    def wildcard(self) -> AstNode:
        return WildcardAstNode()

    def empty_set(self) -> AstNode:
        return EmptySetAstNode()

    def epsilon(self) -> AstNode:
        return EpsilonAstNode()

    def positive_lookahead(self, left: AstNode) -> AstNode:
        return PositiveLookaheadAstNode(left)

    def positive_lookbehind(self, left: AstNode) -> AstNode:
        return PositiveLookbehindAstNode(left)

    def negative_lookahead(self, left: AstNode) -> AstNode:
        return NegativeLookaheadAstNode(left)

    def negative_lookbehind(self, left: AstNode) -> AstNode:
        return NegativeLookbehindAstNode(left)


_PARSER = Lark(
    REGEX_GRAMMAR,
    parser="lalr",
    start="start",
    transformer=RegexAstTransformer(),
)


def build_ast(regex_string: str) -> AstNode:
    """Parse a regular-expression string into the custom AST."""
    if not isinstance(regex_string, str):
        raise TypeError("regex_string must be str")
    return _PARSER.parse(regex_string)


def reverse_ast(node: AstNode) -> AstNode:
    """Reverse an oracle AST. Lookaround must already be lowered."""
    if isinstance(
        node,
        (
            EmptySetAstNode,
            EpsilonAstNode,
            LiteralCharacterAstNode,
            WildcardAstNode,
        ),
    ):
        return node
    if isinstance(node, SeqAstNode):
        return SeqAstNode(reverse_ast(node.right), reverse_ast(node.left))
    if isinstance(node, OrAstNode):
        return OrAstNode(reverse_ast(node.left), reverse_ast(node.right))
    if isinstance(node, StarAstNode):
        return StarAstNode(reverse_ast(node.left))
    if isinstance(node, OracleAstNode):
        return node
    raise TypeError(f"Invalid oracle AST node: {type(node).__name__}")


class Direction(Enum):
    L2R = auto()
    R2L = auto()


class Context:
    def __init__(self) -> None:
        self.id = 0
        self.tapes: dict[int, list[bool]] = {}

    def add_tape(self, tape: list[bool]) -> int:
        oracle_id = self.id
        self.id += 1
        self.tapes[oracle_id] = tape
        return oracle_id


def Eval(
    direction: Direction,
    ast: AstNode,
    text: str,
    context: Context,
) -> list[bool]:
    """Evaluate an AST and return its Boolean match tape."""
    oracle_ast = EvalAux(ast, text, context)
    return Match(direction, oracle_ast, text, context.tapes)


def EvalAux(node: AstNode, text: str, context: Context) -> AstNode:
    """Compute nested lookaround tapes and lower lookaround to oracle nodes."""

    def register(direction: Direction, body: AstNode) -> int:
        return context.add_tape(Match(direction, body, text, context.tapes))

    return _lower_lookarounds(node, register)


def _lower_lookarounds(
    node: AstNode,
    register: Callable[[Direction, AstNode], int],
) -> AstNode:
    """Register each assertion after all assertions in its body."""
    if isinstance(
        node,
        (
            EmptySetAstNode,
            EpsilonAstNode,
            LiteralCharacterAstNode,
            WildcardAstNode,
            OracleAstNode,
        ),
    ):
        return node
    if isinstance(node, SeqAstNode):
        return SeqAstNode(
            _lower_lookarounds(node.left, register),
            _lower_lookarounds(node.right, register),
        )
    if isinstance(node, OrAstNode):
        return OrAstNode(
            _lower_lookarounds(node.left, register),
            _lower_lookarounds(node.right, register),
        )
    if isinstance(node, StarAstNode):
        return StarAstNode(_lower_lookarounds(node.left, register))
    if isinstance(node, (PositiveLookaheadAstNode, NegativeLookaheadAstNode)):
        direction = Direction.R2L
    elif isinstance(node, (PositiveLookbehindAstNode, NegativeLookbehindAstNode)):
        direction = Direction.L2R
    else:
        raise TypeError(f"Invalid AST node: {type(node).__name__}")

    body = _lower_lookarounds(node.left, register)
    oracle_id = register(direction, body)
    if isinstance(node, (NegativeLookaheadAstNode, NegativeLookbehindAstNode)):
        return OracleAstNode(oracle_id, OraclePolarity.NEGATIVE)
    return OracleAstNode(oracle_id, OraclePolarity.POSITIVE)


@dataclass(frozen=True)
class OracleEdge:
    oracle_id: int
    pole: OraclePolarity


class WildcardTransition(Enum):
    ANY = auto()


TransitionSymbol: TypeAlias = (
    str | None | OracleEdge | WildcardTransition
)
Transitions: TypeAlias = dict[int, dict[TransitionSymbol, set[int]]]


class NFA:
    def __init__(
        self,
        starting_state: int,
        final_state: int,
        transitions: Transitions,
    ) -> None:
        self.starting_state = starting_state
        self.final_state = final_state
        self.transitions = transitions

    @property
    def states(self) -> set[int]:
        return set(self.transitions)

    def move(self, states: set[int], char: str) -> set[int]:
        destinations: set[int] = set()
        for state in states:
            destinations.update(self.transitions[state].get(char, ()))
            destinations.update(
                self.transitions[state].get(
                    WildcardTransition.ANY,
                    (),
                )
            )
        return destinations


class ThompsonConstruction:
    def __init__(self, ast: AstNode) -> None:
        self.ast = ast
        self.transitions: Transitions = {}
        self.next_state = 0

    def construct(self) -> NFA:
        self.transitions = {}
        self.next_state = 0
        start, final = self._construct_from_ast(self.ast)
        return NFA(start, final, self.transitions)

    def _new_state(self) -> int:
        state = self.next_state
        self.next_state += 1
        self.transitions[state] = {}
        return state

    def _add_edge(
        self,
        source: int,
        symbol: TransitionSymbol,
        destination: int,
    ) -> None:
        self.transitions[source].setdefault(symbol, set()).add(destination)

    def _construct_from_ast(self, node: AstNode) -> tuple[int, int]:
        if isinstance(node, EmptySetAstNode):
            return self._new_state(), self._new_state()
        if isinstance(node, EpsilonAstNode):
            start = self._new_state()
            final = self._new_state()
            self._add_edge(start, None, final)
            return start, final
        if isinstance(node, LiteralCharacterAstNode):
            if not isinstance(node.char, str) or len(node.char) != 1:
                raise ValueError("A literal node must contain one character")
            start = self._new_state()
            final = self._new_state()
            self._add_edge(start, node.char, final)
            return start, final
        if isinstance(node, WildcardAstNode):
            start = self._new_state()
            final = self._new_state()
            self._add_edge(
                start,
                WildcardTransition.ANY,
                final,
            )
            return start, final
        if isinstance(node, OracleAstNode):
            start = self._new_state()
            final = self._new_state()
            self._add_edge(
                start,
                OracleEdge(node.oracle_id, node.pole),
                final,
            )
            return start, final
        if isinstance(node, SeqAstNode):
            left_start, left_final = self._construct_from_ast(node.left)
            right_start, right_final = self._construct_from_ast(node.right)
            self._add_edge(left_final, None, right_start)
            return left_start, right_final
        if isinstance(node, OrAstNode):
            left_start, left_final = self._construct_from_ast(node.left)
            right_start, right_final = self._construct_from_ast(node.right)
            start = self._new_state()
            final = self._new_state()
            self._add_edge(start, None, left_start)
            self._add_edge(start, None, right_start)
            self._add_edge(left_final, None, final)
            self._add_edge(right_final, None, final)
            return start, final
        if isinstance(node, StarAstNode):
            sub_start, sub_final = self._construct_from_ast(node.left)
            start = self._new_state()
            final = self._new_state()
            self._add_edge(start, None, final)
            self._add_edge(start, None, sub_start)
            self._add_edge(sub_final, None, sub_start)
            self._add_edge(sub_final, None, final)
            return start, final
        raise TypeError(
            f"Unsupported AST node in Thompson construction: "
            f"{type(node).__name__}"
        )


def oracle_closure(
    nfa: NFA,
    states: set[int],
    position: int,
    tapes: Mapping[int, Sequence[bool]],
) -> set[int]:
    """Follow epsilon edges and enabled oracle edges."""
    found = set(states)
    stack = list(states)

    while stack:
        state = stack.pop()
        for symbol, destinations in nfa.transitions[state].items():
            enabled = symbol is None

            if isinstance(symbol, OracleEdge):
                if symbol.oracle_id not in tapes:
                    raise ValueError(
                        f"Oracle {symbol.oracle_id} has not been evaluated"
                    )
                value = tapes[symbol.oracle_id][position]
                if symbol.pole is OraclePolarity.POSITIVE:
                    enabled = value
                elif symbol.pole is OraclePolarity.NEGATIVE:
                    enabled = not value
                else:
                    raise ValueError(f"Invalid oracle polarity: {symbol.pole}")

            if not enabled:
                continue

            for destination in destinations:
                if destination not in found:
                    found.add(destination)
                    stack.append(destination)

    return found


def _compile_onfa(direction: Direction, ast: AstNode) -> NFA:
    if direction is Direction.R2L:
        ast = reverse_ast(ast)
    return ThompsonConstruction(ast).construct()


def Match(
    direction: Direction,
    ast: AstNode,
    text: str,
    tapes: dict[int, list[bool]],
) -> list[bool]:
    """Construct an ONFA and simulate it in the requested direction."""
    nfa = _compile_onfa(direction, ast)

    if direction is Direction.L2R:
        return SimulateL2R(nfa, text, tapes)
    if direction is Direction.R2L:
        return SimulateR2L(nfa, text, tapes)
    raise ValueError(f"Invalid direction: {direction!r}")


def SimulateL2R(
    nfa: NFA,
    text: str,
    tapes: dict[int, list[bool]],
) -> list[bool]:
    n = len(text)
    output = [False] * (n + 1)
    current_states: set[int] = set()

    for position in range(n + 1):
        current_states.add(nfa.starting_state)
        current_states = oracle_closure(
            nfa,
            current_states,
            position,
            tapes,
        )
        if nfa.final_state in current_states:
            output[position] = True
        if position < n:
            current_states = nfa.move(current_states, text[position])

    return output


def SimulateR2L(
    nfa: NFA,
    text: str,
    tapes: dict[int, list[bool]],
) -> list[bool]:
    n = len(text)
    output = [False] * (n + 1)
    current_states: set[int] = set()

    for position in range(n, -1, -1):
        current_states.add(nfa.starting_state)
        current_states = oracle_closure(
            nfa,
            current_states,
            position,
            tapes,
        )
        if nfa.final_state in current_states:
            output[position] = True
        if position > 0:
            current_states = nfa.move(current_states, text[position - 1])

    return output


def _simulate_one_pass(
    direction: Direction, machines: list[NFA], text: str
) -> list[bool]:
    """Single-direction evaluation from Fig. 5, adapted to substring matching.

    Mamouras & Chattopadhyay, POPL 2024, §5.2, doi:10.1145/3632934.
    Rows are in dependency order, with the main ONFA last. One-cell tapes
    at index 0 let both strategies use the same oracle closure.
    """
    n = len(text)
    if direction is Direction.R2L:
        positions, last, offset = range(n, -1, -1), 0, -1
    else:
        positions, last, offset = range(n + 1), n, 0

    output = [False] * (n + 1)
    active: list[set[int]] = [set() for _ in machines]
    column: dict[int, tuple[bool]] = {}
    main_row = len(machines) - 1
    for position in positions:
        char = text[position + offset] if position != last else None
        column.clear()  # Only rows already evaluated at this boundary are visible.
        for row, nfa in enumerate(machines):
            # The other endpoint of a substring can be any boundary.
            seeds = active[row]
            seeds.add(nfa.starting_state)
            closed = oracle_closure(nfa, seeds, 0, column)
            column[row] = (True,) if nfa.final_state in closed else (False,)
            if char is not None:
                active[row] = nfa.move(closed, char)
        output[position] = column[main_row][0]
    return output


Strategy: TypeAlias = Literal["auto", "baseline", "one_pass"]


def evaluate_ast(
    ast: AstNode,
    text: str,
    *,
    strategy: Strategy = "auto",
    direction: Direction = Direction.R2L,
) -> list[bool]:
    """Return the Boolean tape of substring starts (R2L) or ends (L2R).

    With auto, fuse all ONFAs if they have the same scan direction.
    With baseline, materialize each assertion tape. With one_pass, require
    a common direction. All modes include boundaries 0 and len(text).
    """
    if direction not in (Direction.R2L, Direction.L2R):
        raise ValueError(f"Invalid direction: {direction!r}")
    if strategy == "baseline":
        return Eval(direction, ast, text, Context())
    if strategy not in ("auto", "one_pass"):
        raise ValueError(f"Unknown strategy: {strategy!r}")

    assertions: list[tuple[Direction, AstNode]] = []

    def register(scan: Direction, body: AstNode) -> int:
        oracle_id = len(assertions)
        assertions.append((scan, body))
        return oracle_id

    main = _lower_lookarounds(ast, register)
    if not assertions:
        return Match(direction, main, text, {})
    if any(scan is not direction for scan, _ in assertions):
        if strategy == "one_pass":
            raise ValueError(
                "one_pass requires all assertions to share the main scan direction"
            )
        tapes: dict[int, list[bool]] = {}
        for row, (scan, body) in enumerate(assertions):
            tapes[row] = Match(scan, body, text, tapes)
        return Match(direction, main, text, tapes)

    machines = [_compile_onfa(scan, body) for scan, body in assertions]
    machines.append(_compile_onfa(direction, main))
    return _simulate_one_pass(direction, machines, text)


def substring_match(
    regex_string: str, text: str, *, strategy: Strategy = "auto"
) -> list[int]:
    """Return every boundary at which a matching substring starts."""
    tape = evaluate_ast(build_ast(regex_string), text, strategy=strategy)
    return [position for position, matched in enumerate(tape) if matched]

