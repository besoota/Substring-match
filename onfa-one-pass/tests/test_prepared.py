import itertools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from onfa_regex import build_ast, evaluate_ast, prepare_match
from onfa_regex import engine


@pytest.mark.parametrize("pattern", [
    "(a*)*(?=.*b.*)",
    "a*(?=.*b.*)",
    "(?=.*a.*)(?=.*b.*)",
    "ab|ba",
    "(?=a(?=b))a",
    "(?<=a)b(?!a)",
    "(?<!(?=b)b)a",
    "(?!.)",
])
def test_prepared_is_the_positive_lookahead_of_the_whole_expression(pattern):
    reference = re.compile(f"(?={pattern})", re.DOTALL)
    ast = build_ast(pattern)
    texts = (
        "".join(chars) for length in range(5)
        for chars in itertools.product("ab", repeat=length)
    )
    for text in itertools.chain(texts, ["a\n", "あb"]):
        expected = [reference.match(text, i) is not None for i in range(len(text) + 1)]
        assert prepare_match(ast, text).start_tape() == expected
        assert evaluate_ast(ast, text) == expected


@pytest.mark.parametrize(("pattern", "text", "expected"), [
    ("ε", "", [True]),
    ("∅", "", [False]),
    ("(?!∅)", "ab", [True, True, True]),
    ("(?<=a*)b", "abb", [False, True, True, False]),
])
def test_prepared_empty_and_variable_width_assertions(pattern, text, expected):
    assert prepare_match(build_ast(pattern), text).start_tape() == expected


@pytest.mark.parametrize("legacy", [False, True], ids=["prepared-api", "legacy-engine"])
def test_prepare_evaluates_only_inner_assertions_and_reuses_the_main_onfa(monkeypatch, legacy):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "experiments"))
    import linear_scaling as experiment

    if legacy:
        monkeypatch.delattr(engine, "prepare_match")
    compiled = []
    simulated = []
    construct = engine.ThompsonConstruction.construct
    simulate = engine.SimulateR2L

    def record_construct(builder):
        nfa = construct(builder)
        compiled.append(nfa)
        return nfa

    def record_simulation(nfa, text, tapes):
        simulated.append(nfa)
        return simulate(nfa, text, tapes)

    monkeypatch.setattr(engine.ThompsonConstruction, "construct", record_construct)
    monkeypatch.setattr(engine, "SimulateR2L", record_simulation)
    scan = experiment.prepare_scan(build_ast("(?=.*a.*)(?=.*b.*)"), "aba")
    assert len(compiled) == 3
    assert simulated == compiled[:2]
    main_onfa = compiled[-1]

    first = scan()
    assert first == [True, True, False, False]
    first[0] = False
    assert scan() == [True, True, False, False]
    assert len(compiled) == 3
    assert simulated == [*compiled[:2], main_onfa, main_onfa]


def test_equal_length_inputs_keep_separate_matrices():
    ast = build_ast("a(?=b)")
    yes = prepare_match(ast, "ab")
    no = prepare_match(ast, "aa")
    assert no.start_tape() == [False, False, False]
    assert yes.start_tape() == [True, False, False]


@pytest.mark.parametrize("strategy_args", [[], ["--strategy", "prepared"]])
def test_benchmark_excludes_precomputation_and_times_every_new_scan(monkeypatch, strategy_args):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "experiments"))
    import linear_scaling as experiment

    clock = 0
    preparations = []
    scans = []

    def prepare(ast, text):
        nonlocal clock
        clock += 1000
        preparations.append(len(text))

        def scan():
            nonlocal clock
            clock += 11
            scans.append(len(text))
            return [False] * (len(text) + 1)

        return scan

    def reference(ast, text):
        nonlocal clock
        clock += 99
        return [False] * (len(text) + 1)

    monkeypatch.setattr(experiment, "prepare_scan", prepare)
    monkeypatch.setattr(engine, "evaluate_ast", reference)
    monkeypatch.setattr(experiment, "time", SimpleNamespace(perf_counter_ns=lambda: clock))
    monkeypatch.setattr(experiment, "TEXT_LENGTHS", [3, 5])
    monkeypatch.setattr(experiment.sys, "argv", ["linear_scaling.py", *strategy_args])
    strategy = experiment.parse_args().strategy
    assert strategy == "prepared"
    raw, summary = experiment.benchmark(["two_lookaheads"], 2, 1, strategy)
    assert preparations == [3, 5]
    assert scans == [3, 3, 3, 5, 5, 5]
    assert [row["elapsed_ns"] for row in raw] == [11] * 4
    assert [row["prepare_once_ns"] for row in summary] == [1000, 1000]


def test_direct_script_prefers_local_source_with_older_package_exports(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / "project"
    scripts = project / "experiments"
    scripts.mkdir(parents=True)
    shutil.copy2(root / "experiments" / "linear_scaling.py", scripts)
    package = project / "src" / "onfa_regex"
    package.mkdir(parents=True)
    shutil.copy2(root / "src" / "onfa_regex" / "engine.py", package)
    (package / "__init__.py").write_text(
        "from .engine import build_ast, evaluate_ast\n", encoding="utf-8"
    )
    decoy = tmp_path / "other_install" / "onfa_regex"
    decoy.mkdir(parents=True)
    (decoy / "__init__.py").write_text(
        "raise AssertionError('imported the wrong package')\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(decoy.parent), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [sys.executable, str(scripts / "linear_scaling.py"), "--help"],
        cwd=tmp_path, env=env, text=True, capture_output=True, check=True,
    )
    assert "default: prepared" in result.stdout
