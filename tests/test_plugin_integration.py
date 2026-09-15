"""End-to-end checks: a real pytest session driving the plugin."""

import json

import pytest

from llm_fuzz_ci.schema import make_case, write_cases

pytest_plugins = ["pytester"]

HARNESS = """
    import pytest
    from app import divide

    @pytest.mark.llm_fuzz(budget_usd=0.05)
    def test_divide(llm_fuzz_case):
        '''Division must not leak a raw ZeroDivisionError.'''
        try:
            result = divide(**llm_fuzz_case.input)
        except ZeroDivisionError:
            pytest.fail("divide should handle y=0")
        assert result is None or isinstance(result, (int, float))
"""


@pytest.fixture
def project(pytester):
    pytester.makepyfile(app="def divide(x, y):\n    return x / y\n")
    pytester.makepyfile(test_divide=HARNESS)
    return pytester


def run(pytester, *extra):
    report = pytester.path / "report.json"
    result = pytester.runpytest(
        "-p", "no:llm_fuzz_ci", "-p", "llm_fuzz_ci.pytest_plugin",
        f"--llm-fuzz-corpus-dir={pytester.path / 'cases'}",
        f"--llm-fuzz-report={report}",
        *extra,
    )
    saved = json.loads(report.read_text()) if report.exists() else None
    return result, saved


def test_collect_writes_the_marked_targets(project):
    targets = project.path / "targets.json"
    project.runpytest(
        "-p", "no:llm_fuzz_ci", "-p", "llm_fuzz_ci.pytest_plugin",
        "--collect-only", "-q", f"--llm-fuzz-collect-targets={targets}",
    )

    saved = json.loads(targets.read_text())["targets"]
    assert [t["id"] for t in saved] == ["test_divide.py::test_divide"]
    assert saved[0]["budget_usd"] == 0.05
    assert saved[0]["description"] == "Division must not leak a raw ZeroDivisionError."


def test_each_saved_input_becomes_one_test(project):
    write_cases(
        project.path / "cases",
        [
            make_case(target_id="test_divide.py::test_divide", input_value={"x": 1, "y": 0}),
            make_case(target_id="test_divide.py::test_divide", input_value={"x": 4, "y": 2}),
        ],
    )

    result, saved = run(project)

    result.assert_outcomes(passed=1, failed=1)
    assert saved["summary"] == {"executed_cases": 2, "failed_cases": 1, "passed_cases": 1}
    assert {r["outcome"] for r in saved["results"]} == {"passed", "failed"}
    assert any("divide should handle y=0" in r.get("failure", "") for r in saved["results"])


def test_a_target_with_no_inputs_is_skipped_by_default(project):
    result, saved = run(project)

    result.assert_outcomes(skipped=1)
    assert saved["summary"]["executed_cases"] == 0


def test_require_cases_records_the_missing_target_in_the_report(project):
    """A red run that reports zero failures is worse than no report at all."""
    result, saved = run(project, "--llm-fuzz-require-cases")

    assert result.ret != 0
    assert saved["summary"]["failed_cases"] == 1
    entry = saved["results"][0]
    assert entry["target_id"] == "test_divide.py::test_divide"
    assert entry["outcome"] == "failed"
    assert "No saved inputs" in entry["failure"]


def test_inputs_for_an_unknown_target_are_never_run(project):
    write_cases(
        project.path / "cases",
        [make_case(target_id="test_divide.py::test_typo", input_value={"x": 1, "y": 0})],
    )

    result, saved = run(project)

    result.assert_outcomes(skipped=1)
    assert saved["results"] == []


def test_the_marker_is_required_to_use_the_fixture(pytester):
    pytester.makepyfile("def test_x(llm_fuzz_case):\n    assert llm_fuzz_case\n")

    result = pytester.runpytest(
        "-p", "no:llm_fuzz_ci", "-p", "llm_fuzz_ci.pytest_plugin"
    )

    assert result.ret != 0
    assert "requires @pytest.mark.llm_fuzz" in str(result.stdout) + str(result.stderr)
