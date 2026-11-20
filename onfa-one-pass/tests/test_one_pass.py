import itertools
import re

import pytest

from onfa_regex import Context, Direction, Eval, build_ast, evaluate_ast, substring_match
from onfa_regex import engine


STUDY_PATTERNS = (
    "(a*)*(?=.*b.*)",
    "a*(?=.*b.*)",
    "(?=.*a.*)(?=.*b.*)",
)
SMALL_TEXTS = [
    "".join(chars)
    for length in range(5)
    for chars in itertools.product("ab", repeat=length)
] + ["ab\nb", "a.あ", "あ.a", "bbbba", "aaabb"]


@pytest.mark.parametrize("pattern", [
    *STUDY_PATTERNS,
    "(?=b)",
    "(?!b)",
    "(?=a(?=b))a(?!c)",
    "(?!(?!ab))ab",
    "(?!a(?=b))a",
    "((?=ab)a|b)*(?!.)",
    "a(?=b)|(?=a)b",
    "a*(?=a*)",
    "(?=.)*(?=a)a",
    r"(?=\.)\.",
    "(?=.*あ).",
])
def test_starts_at_every_boundary(pattern):
    ast = build_ast(pattern)
    reference = re.compile(pattern, re.DOTALL)
    for text in SMALL_TEXTS:
        expected = [reference.match(text, pos) is not None for pos in range(len(text) + 1)]
        assert evaluate_ast(ast, text, strategy="baseline") == expected
        assert evaluate_ast(ast, text, strategy="one_pass") == expected
        assert evaluate_ast(ast, text) == expected


@pytest.mark.parametrize(("pattern", "text", "expected"), [
    ("(?=ε)", "", [0]),
    ("(?!ε)", "ab", []),
    ("(?=∅)", "ab", []),
    ("(?!∅)", "ab", [0, 1, 2]),
    ("(?=ε|a)(?!.)", "ab", [2]),
    ("(?=a)(?=b)", "ab", []),
    ("ε", "", [0]),
    ("∅", "", []),
])
def test_empty_language_and_zero_width(pattern, text, expected):
    for mode in ("baseline", "one_pass", "auto"):
        assert substring_match(pattern, text, strategy=mode) == expected


@pytest.mark.parametrize("pattern", [
    "(?<=a)b",
    "(?<=(?<=a)b)c|(?<!a)b",
    "(?<=a)(?<!ba)",
    "a*(?<!b)",
])
def test_left_to_right_returns_end_boundaries(pattern):
    ast = build_ast(pattern)
    reference = re.compile(pattern, re.DOTALL)
    for text in [*SMALL_TEXTS, "abcabc"]:
        expected = [
            any(reference.fullmatch(text, start, end) is not None for start in range(end + 1))
            for end in range(len(text) + 1)
        ]
        for mode in ("one_pass", "auto", "baseline"):
            assert evaluate_ast(ast, text, direction=Direction.L2R, strategy=mode) == expected


@pytest.mark.parametrize("pattern", [
    "(?<=a)b",
    "(?=a(?<=a))a",
    "(?<=(?=a)a)(?!a)",
    "(?<=a*b)a",
])
def test_start_tape_with_lookbehind_uses_baseline_or_rejects_strict_mode(pattern):
    ast = build_ast(pattern)
    for text in SMALL_TEXTS:
        assert evaluate_ast(ast, text) == Eval(Direction.R2L, ast, text, Context())
    with pytest.raises(ValueError, match="scan direction"):
        evaluate_ast(ast, "aba", strategy="one_pass")


def test_end_tape_with_lookahead_uses_fallback():
    ast = build_ast("a(?=b)")
    assert evaluate_ast(ast, "abab", direction=Direction.L2R) == [False, True, False, True, False]
    with pytest.raises(ValueError, match="scan direction"):
        evaluate_ast(ast, "abab", direction=Direction.L2R, strategy="one_pass")


def test_partially_lowered_ast_cannot_read_its_own_oracle():
    query = engine.OracleAstNode(0, engine.OraclePolarity.POSITIVE)
    ast = engine.PositiveLookaheadAstNode(query)
    for mode in ("one_pass", "auto", "baseline"):
        with pytest.raises(ValueError, match="has not been evaluated"):
            evaluate_ast(ast, "ab", strategy=mode)


class ObservedText(str):
    def __init__(self, value):
        self.reads = []

    def __getitem__(self, index):
        self.reads.append(index)
        return super().__getitem__(index)


@pytest.mark.parametrize(("pattern", "direction"), [
    ("(?=a(?=b))a(?!c)", Direction.R2L),
    ("(?<=(?<=a)b)c(?<!d)", Direction.L2R),
])
def test_auto_reads_each_character_once_and_uses_one_cell_per_row(monkeypatch, pattern, direction):
    text = ObservedText("abcabc")
    ast = build_ast(pattern)
    positions = list(range(len(text)))
    if direction is Direction.R2L:
        positions.reverse()

    baseline = evaluate_ast(ast, text, direction=direction, strategy="baseline")
    assert text.reads == positions * 4  # Three assertions and the main ONFA.
    text.reads.clear()
    closure = engine.oracle_closure
    row_calls = 0

    def observe(nfa, states, position, tapes):
        nonlocal row_calls
        assert position == 0
        assert all(len(slot) == 1 for slot in tapes.values())
        row_calls += 1
        return closure(nfa, states, position, tapes)

    monkeypatch.setattr(engine, "oracle_closure", observe)
    assert evaluate_ast(ast, text, direction=direction) == baseline
    assert text.reads == positions
    assert row_calls == 4 * (len(text) + 1)
