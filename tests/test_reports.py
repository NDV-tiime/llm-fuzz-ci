from llm_fuzz_ci.alerts import format_alert_body
from llm_fuzz_ci.reports import format_replay_report_markdown, format_replay_report_text


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
    rendered = format_replay_report_text(_sample_report(), include_failure=True)

    assert "Failed: 1" in rendered
    assert '"y": 0' in rendered
    assert "AssertionError: divide should guard y=0" in rendered
    assert "\x1b" not in rendered


def test_markdown_report_uses_json_code_blocks():
    rendered = format_replay_report_markdown(_sample_report())

    assert "```json" in rendered
    assert '"x": 1' in rendered
    assert "divide-happy-path" not in rendered


def test_alert_body_includes_readable_input_block():
    rendered = format_alert_body(_sample_report())

    assert "Input:" in rendered
    assert "```json" in rendered
    assert '"y": 0' in rendered
