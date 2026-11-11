from onfa_regex import build_ast, evaluate_ast, substring_match


def test_literal_substring_matching():
    assert substring_match("a", "baab") == [1, 2]


def test_positive_lookahead():
    assert substring_match("a(?=a)", "aaa") == [0, 1]


def test_positive_lookbehind():
    assert substring_match("(?<=a)a", "aaa") == [1, 2]


def test_negative_lookahead():
    assert substring_match("a(?!a)", "aaa") == [2]


def test_negative_lookbehind():
    assert substring_match("(?<!a)a", "aaa") == [0]


def test_preparsed_ast_produces_tape():
    ast = build_ast("aa")
    assert evaluate_ast(ast, "aaa") == [True, True, False, False]

