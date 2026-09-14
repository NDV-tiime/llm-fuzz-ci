from llm_fuzz_ci.alerts import format_alert_body
from llm_fuzz_ci.reports import (
    format_cases_markdown,
    format_full_report_markdown,
    format_test_report_markdown,
    format_test_report_text,
)
from llm_fuzz_ci.schema import make_case


def _sample_report():
    return {
        "generated_at": "2026-09-11T13:54:35Z",
        "summary": {
            "executed_cases": 2,
            "passed_cases": 1,
            "failed_cases": 1,
        },
        "results": [
            {
                "target_id": "divide",
                "case_id": "divide-zero",
                "nodeid": "tests/test_app.py::test_divide[divide-zero]",
                "outcome": "failed",
                "category": "zero-denominator",
                "input": {"x": 1, "y": 0},
                "rationale": "Division by zero should be handled.",
                "failure": "\x1b[31mE   AssertionError: divide should guard y=0\x1b[0m",
            },
            {
                "target_id": "divide",
                "case_id": "divide-happy-path",
                "nodeid": "tests/test_app.py::test_divide[divide-happy-path]",
                "outcome": "passed",
                "category": "normal",
                "input": {"x": 4, "y": 2},
                "rationale": "Simple successful division.",
            },
        ],
        "failures": [
            {
                "target_id": "divide",
                "case_id": "divide-zero",
                "nodeid": "tests/test_app.py::test_divide[divide-zero]",
                "outcome": "failed",
                "category": "zero-denominator",
                "input": {"x": 1, "y": 0},
                "rationale": "Division by zero should be handled.",
                "failure": "\x1b[31mE   AssertionError: divide should guard y=0\x1b[0m",
            }
        ],
    }


def test_text_report_shows_failing_input_and_failure_excerpt():
    rendered = format_test_report_text(_sample_report(), include_failure=True)

    assert "Failed: 1" in rendered
    assert '"y": 0' in rendered
    assert "AssertionError: divide should guard y=0" in rendered
    assert "\x1b" not in rendered


def test_markdown_report_shows_generated_inputs_readably():
    rendered = format_test_report_markdown(_sample_report(), failures_only=False)

    assert "# LLM Fuzz CI Test Report" in rendered
    assert "`x`: `1`" in rendered
    assert "`y`: `0`" in rendered
    assert "divide-happy-path" in rendered


def test_generated_cases_report_groups_inputs_by_target():
    rendered = format_cases_markdown(
        [
            make_case(
                target_id="divide",
                input_value={"x": 1, "y": 0},
                category="zero-denominator",
                rationale="Checks division by zero.",
            )
        ]
    )

    assert "# LLM Fuzz CI Generated Inputs" in rendered
    assert "## divide" in rendered
    assert "`x`: `1`" in rendered
    assert "Checks division by zero." in rendered


def test_alert_body_includes_readable_input_block():
    rendered = format_alert_body(_sample_report())

    assert "Input:" in rendered
    assert "```json" in rendered
    assert '"y": 0' in rendered


def _sample_cases():
    return [
        make_case(
            target_id="divide",
            input_value={"x": 1, "y": 0},
            category="zero-denominator",
            rationale="Division by zero should be handled.",
        ),
        make_case(
            target_id="divide",
            input_value={"x": 4, "y": 2},
            category="normal",
            rationale="Simple successful division.",
        ),
    ]


def _full_report_input():
    cases = _sample_cases()
    report = {
        "generated_at": "2026-09-11T13:54:35Z",
        "exitstatus": 1,
        "summary": {"executed_cases": 2, "passed_cases": 1, "failed_cases": 1},
        "results": [
            {
                "case_id": cases[0].id,
                "target_id": "divide",
                "nodeid": "tests/test_app.py::test_divide[zero]",
                "outcome": "failed",
                "category": "zero-denominator",
                "input": {"x": 1, "y": 0},
                "rationale": "Division by zero should be handled.",
                "failure": "E   AssertionError: divide should guard y=0",
            },
            {
                "case_id": cases[1].id,
                "target_id": "divide",
                "nodeid": "tests/test_app.py::test_divide[happy]",
                "outcome": "passed",
                "category": "normal",
                "input": {"x": 4, "y": 2},
                "rationale": "Simple successful division.",
            },
        ],
    }
    return cases, report


def test_full_report_merges_each_input_with_its_outcome():
    cases, report = _full_report_input()

    rendered = format_full_report_markdown(cases=cases, test_report=report)

    assert rendered.startswith("# LLM Fuzz CI Report")
    assert "| Generated inputs | `2` |" in rendered
    assert "| Passed | `1` |" in rendered
    assert "| Failed | `1` |" in rendered
    assert "**1 generated input(s) failed a marked test.**" in rendered
    # Each input is listed once per section, never twice within one.
    assert rendered.count("## All Generated Inputs") == 1
    assert rendered.count("`zero-denominator`") == 2  # failures section + full list
    assert rendered.count("`normal`") == 1  # passing input only in the full list
    # The failure excerpt belongs to the failures section alone.
    assert rendered.count("divide should guard y=0") == 1
    assert rendered.index("## Failing Inputs") < rendered.index("## All Generated Inputs")


def test_full_report_marks_inputs_that_no_test_consumed():
    cases, report = _full_report_input()
    report["results"] = report["results"][:1]
    report["exitstatus"] = 1

    rendered = format_full_report_markdown(cases=cases, test_report=report)

    assert "| Not tested | `1` |" in rendered
    assert "`not tested`" in rendered
    assert "1 input(s) — 0 passed, 1 failed, 1 not tested." not in rendered
    assert "2 input(s) — 0 passed, 1 failed, 1 not tested." in rendered


def test_full_report_reports_a_failed_run_with_no_recorded_failures():
    rendered = format_full_report_markdown(
        cases=_sample_cases(),
        test_report={
            "generated_at": "2026-09-11T13:54:35Z",
            "exitstatus": 1,
            "summary": {"executed_cases": 0, "passed_cases": 0, "failed_cases": 0},
            "results": [],
        },
    )

    assert "**The test run failed without recording a generated-input failure.**" in rendered
    assert "No generated input failed its marked test." in rendered


def test_full_report_without_a_test_report_covers_generated_inputs_only():
    rendered = format_full_report_markdown(cases=_sample_cases())

    assert "No test results were recorded." in rendered
    assert "| Generated inputs | `2` |" in rendered
    assert "| Passed |" not in rendered


def test_full_report_renders_token_usage_when_available():
    rendered = format_full_report_markdown(
        cases=_sample_cases(),
        usage_report={
            "agent": "codex",
            "model": "gpt-5.6-terra",
            "usage": {"input_tokens": 110163, "total_tokens": 117136},
        },
    )

    assert "| Agent | `codex` |" in rendered
    assert "| Model | `gpt-5.6-terra` |" in rendered
    assert "| Total tokens | `117,136` |" in rendered


def test_multiline_input_stays_inside_its_markdown_list_item():
    """An unindented fence body ends the list item and swallows the rest of the report."""
    rendered = format_cases_markdown(
        [
            make_case(
                target_id="prompts",
                input_value={"message": "first line\nsecond line"},
                category="prompt-boundary",
                rationale="Multi-line payload.",
            )
        ]
    )

    body = rendered.split("```text\n", 1)[1].split("\n  ```", 1)[0]
    assert body.splitlines() == ["  first line", "  second line"]


def test_fenced_input_is_wrapped_in_a_longer_fence_than_its_content():
    rendered = format_cases_markdown(
        [
            make_case(
                target_id="prompts",
                input_value={"message": "```json\n{}\n```"},
                category="prompt-delimiter-injection",
                rationale="Payload closes a Markdown fence.",
            )
        ]
    )

    assert "  ````text" in rendered
    assert rendered.rstrip().endswith("````")
    assert "'''" not in rendered
