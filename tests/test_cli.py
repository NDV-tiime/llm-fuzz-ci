from argparse import Namespace

from llm_fuzz_ci import cli
from llm_fuzz_ci.generator import GenerationResult
from llm_fuzz_ci.schema import FuzzTarget, load_cases, make_case, write_cases, write_targets


def _generate_args(tmp_path):
    return Namespace(
        agent="codex",
        model=None,
        provider=None,
        max_cases=None,
        max_turns=None,
        max_budget_usd=None,
        timeout_seconds=600,
        show_usage=False,
        usage_report=None,
        corpus_dir=tmp_path / "cases",
        targets=tmp_path / "targets.json",
        reuse_existing_cases=False,
    )


def test_generate_replaces_stale_cases_by_default(tmp_path, monkeypatch):
    write_targets(
        tmp_path / "targets.json",
        [
            FuzzTarget(
                id="divide",
                target="pytest::tests/test_app.py::test_divide",
                budget_usd=0.25,
            )
        ],
    )
    stale = make_case(
        target_id="divide",
        input_value={"x": 1, "y": 0},
        category="zero-denominator",
        rationale="old",
    )
    write_cases(tmp_path / "cases", [stale], merge=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "generate_cases_with_usage", lambda *args, **kwargs: GenerationResult([]))

    assert cli.cmd_generate(_generate_args(tmp_path)) == 0

    assert load_cases(tmp_path / "cases", "divide") == []


def test_generate_can_reuse_existing_cases(tmp_path, monkeypatch):
    write_targets(
        tmp_path / "targets.json",
        [
            FuzzTarget(
                id="divide",
                target="pytest::tests/test_app.py::test_divide",
                budget_usd=0.25,
            )
        ],
    )
    stale = make_case(
        target_id="divide",
        input_value={"x": 1, "y": 0},
        category="zero-denominator",
        rationale="old",
    )
    write_cases(tmp_path / "cases", [stale], merge=False)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "generate_cases_with_usage", lambda *args, **kwargs: GenerationResult([]))
    args = _generate_args(tmp_path)
    args.reuse_existing_cases = True

    assert cli.cmd_generate(args) == 0

    assert [case.input for case in load_cases(tmp_path / "cases", "divide")] == [
        {"x": 1, "y": 0}
    ]
