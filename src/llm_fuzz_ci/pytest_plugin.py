from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from .schema import (
    REPORT_SCHEMA_VERSION,
    FuzzCase,
    FuzzTarget,
    load_cases,
    utc_now,
    write_targets,
)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("llm-fuzz-ci")
    group.addoption(
        "--llm-fuzz-corpus-dir",
        action="store",
        default=".llm-fuzz/cases",
        help="Directory containing saved LLM Fuzz JSONL cases.",
    )
    group.addoption(
        "--llm-fuzz-collect-targets",
        action="store",
        default=None,
        help="Write discovered @pytest.mark.llm_fuzz targets to this JSON file.",
    )
    group.addoption(
        "--llm-fuzz-report",
        action="store",
        default=None,
        help="Write generated input test results to this JSON file.",
    )
    group.addoption(
        "--llm-fuzz-require-cases",
        action="store_true",
        default=False,
        help="Fail marked fuzz tests when no saved cases exist for a target.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "llm_fuzz(budget_usd): declare a budgeted fuzz target for LLM Fuzz CI.",
    )
    config._llm_fuzz_targets = []  # type: ignore[attr-defined]
    config._llm_fuzz_results = []  # type: ignore[attr-defined]


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    targets: list[FuzzTarget] = []
    for item in items:
        marker = item.get_closest_marker("llm_fuzz")
        if marker is None:
            continue
        targets.append(_target_from_marker(item, marker))
    config._llm_fuzz_targets = targets  # type: ignore[attr-defined]


def pytest_collection_finish(session: pytest.Session) -> None:
    output = session.config.getoption("--llm-fuzz-collect-targets")
    if not output:
        return
    targets = session.config._llm_fuzz_targets  # type: ignore[attr-defined]
    write_targets(output, targets)


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "llm_fuzz_case" not in metafunc.fixturenames:
        return
    if metafunc.config.getoption("--llm-fuzz-collect-targets"):
        return

    marker = metafunc.definition.get_closest_marker("llm_fuzz")
    if marker is None:
        raise pytest.UsageError(
            "llm_fuzz_case fixture requires @pytest.mark.llm_fuzz(budget_usd=...)"
        )

    target = _target_from_marker(metafunc.definition, marker)
    corpus_dir = metafunc.config.getoption("--llm-fuzz-corpus-dir")
    require_cases = metafunc.config.getoption("--llm-fuzz-require-cases")
    cases = load_cases(corpus_dir, target.id)

    if not cases:
        if require_cases:
            params = [
                pytest.param(
                    {"__llm_fuzz_missing_target_id": target.id},
                    id="missing-fuzz-cases",
                )
            ]
        else:
            params = [
                pytest.param(
                    {"__llm_fuzz_skip_target_id": target.id},
                    marks=pytest.mark.skip(
                        reason=f"No saved LLM Fuzz cases for target {target.id!r}"
                    ),
                    id="no-fuzz-cases",
                )
            ]
    else:
        params = [pytest.param(case, id=case.id) for case in cases]

    metafunc.parametrize("llm_fuzz_case", params, indirect=True)


@pytest.fixture
def llm_fuzz_case(request: pytest.FixtureRequest) -> FuzzCase:
    value = request.param
    if isinstance(value, dict) and "__llm_fuzz_missing_target_id" in value:
        pytest.fail(
            f"No saved LLM Fuzz cases for target {value['__llm_fuzz_missing_target_id']!r}"
        )
    if isinstance(value, dict) and "__llm_fuzz_skip_target_id" in value:
        pytest.skip(f"No saved LLM Fuzz cases for target {value['__llm_fuzz_skip_target_id']!r}")
    request.node._llm_fuzz_case = value  # type: ignore[attr-defined]
    return value


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]):
    outcome = yield
    report = outcome.get_result()
    if call.when != "call" or not hasattr(item, "_llm_fuzz_case"):
        return

    case = item._llm_fuzz_case  # type: ignore[attr-defined]
    entry = {
        "nodeid": item.nodeid,
        "outcome": report.outcome,
        "duration": report.duration,
        "target_id": case.target_id,
        "case_id": case.id,
        "input": case.input,
        "rationale": case.rationale,
    }
    if report.failed:
        entry["failure"] = report.longreprtext
    item.config._llm_fuzz_results.append(entry)  # type: ignore[attr-defined]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    output = session.config.getoption("--llm-fuzz-report")
    if not output:
        return
    results = session.config._llm_fuzz_results  # type: ignore[attr-defined]
    failures = [result for result in results if result["outcome"] != "passed"]
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "exitstatus": exitstatus,
        "summary": {
            "executed_cases": len(results),
            "failed_cases": len(failures),
            "passed_cases": len(results) - len(failures),
        },
        "results": results,
        "failures": failures,
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _target_from_marker(item: pytest.Item, marker: pytest.Mark) -> FuzzTarget:
    if marker.args:
        raise pytest.UsageError(
            "@pytest.mark.llm_fuzz does not accept positional arguments. "
            "Use @pytest.mark.llm_fuzz(budget_usd=0.25)."
        )
    extra_kwargs = set(marker.kwargs) - {"budget_usd"}
    if extra_kwargs:
        names = ", ".join(sorted(extra_kwargs))
        raise pytest.UsageError(
            f"@pytest.mark.llm_fuzz does not accept keyword arguments: {names}. "
            "Only budget_usd is supported."
        )
    if "budget_usd" not in marker.kwargs:
        raise pytest.UsageError(
            "@pytest.mark.llm_fuzz requires budget_usd, for example "
            "@pytest.mark.llm_fuzz(budget_usd=0.25)."
        )

    source_file = getattr(item, "path", None) or getattr(item, "fspath", None)
    target_id = str(item.nodeid)
    target = f"pytest::{item.nodeid}"
    try:
        return FuzzTarget.from_dict(
            {
                "id": target_id,
                "target": target,
                "budget_usd": marker.kwargs["budget_usd"],
                "description": _item_description(item),
                "language": "python",
                "test_nodeid": item.nodeid,
                "source_file": str(source_file) if source_file is not None else None,
            }
        )
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


def _item_description(item: pytest.Item) -> str | None:
    obj = getattr(item, "obj", None)
    doc = getattr(obj, "__doc__", None)
    if isinstance(doc, str) and doc.strip():
        return " ".join(doc.split())
    return None
