import json
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


def test_cases_command_renders_generated_inputs(tmp_path, capsys):
    write_cases(
        tmp_path / "cases",
        [
            make_case(
                target_id="divide",
                input_value={"x": 1, "y": 0},
                category="zero-denominator",
                rationale="Checks division by zero.",
            )
        ],
        merge=False,
    )

    args = Namespace(
        corpus_dir=tmp_path / "cases",
        format="markdown",
        output=None,
        max_cases=100,
    )

    assert cli.cmd_cases(args) == 0

    rendered = capsys.readouterr().out
    assert "# LLM Fuzz CI Generated Inputs" in rendered
    assert "`x`: `1`" in rendered
    assert "Checks division by zero." in rendered


def test_summary_command_writes_one_combined_markdown_report(tmp_path, capsys):
    case = make_case(
        target_id="divide",
        input_value={"x": 1, "y": 0},
        category="zero-denominator",
        rationale="Checks division by zero.",
    )
    write_cases(tmp_path / "cases", [case], merge=False)
    (tmp_path / "test-report.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-09-11T13:54:35Z",
                "exitstatus": 1,
                "summary": {"executed_cases": 1, "passed_cases": 0, "failed_cases": 1},
                "results": [
                    {
                        "case_id": case.id,
                        "target_id": "divide",
                        "nodeid": "tests/test_app.py::test_divide[zero]",
                        "outcome": "failed",
                        "category": "zero-denominator",
                        "input": {"x": 1, "y": 0},
                        "rationale": "Checks division by zero.",
                        "failure": "E   AssertionError: divide should guard y=0",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "reports" / "llm-fuzz-ci-report.md"
    args = Namespace(
        corpus_dir=tmp_path / "cases",
        report=tmp_path / "test-report.json",
        usage_report=tmp_path / "missing-usage.json",
        output=output,
        max_cases=100,
    )

    assert cli.cmd_summary(args) == 0

    rendered = output.read_text(encoding="utf-8")
    assert rendered.startswith("# LLM Fuzz CI Report")
    assert "**1 generated input(s) failed a marked test.**" in rendered
    assert "divide should guard y=0" in rendered
    assert "## Token Usage" not in rendered
    assert str(output) in capsys.readouterr().out


def test_summary_command_runs_without_a_test_report(tmp_path):
    write_cases(
        tmp_path / "cases",
        [make_case(target_id="divide", input_value={"x": 1, "y": 0})],
        merge=False,
    )
    output = tmp_path / "reports" / "llm-fuzz-ci-report.md"
    args = Namespace(
        corpus_dir=tmp_path / "cases",
        report=tmp_path / "missing-report.json",
        usage_report=tmp_path / "missing-usage.json",
        output=output,
        max_cases=100,
    )

    assert cli.cmd_summary(args) == 0
    assert "No test results were recorded." in output.read_text(encoding="utf-8")
