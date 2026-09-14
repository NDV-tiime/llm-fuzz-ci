from __future__ import annotations

import json
import re
from typing import Any


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def format_test_report_text(
    report: dict[str, Any],
    *,
    failures_only: bool = True,
    max_cases: int = 25,
    include_failure: bool = False,
) -> str:
    summary = report.get("summary", {})
    entries = _selected_entries(report, failures_only=failures_only)
    shown = entries[:max_cases]
    title = "LLM Fuzz CI Test Report"
    lines = [
        title,
        "=" * len(title),
        f"Generated: {report.get('generated_at', 'unknown')}",
        f"Executed: {summary.get('executed_cases', 0)}",
        f"Passed: {summary.get('passed_cases', 0)}",
        f"Failed: {summary.get('failed_cases', 0)}",
        "",
    ]
    if not shown:
        lines.append("No failed generated inputs found." if failures_only else "No generated inputs found.")
        return "\n".join(lines)

    for index, entry in enumerate(shown, start=1):
        outcome = str(entry.get("outcome", "unknown")).upper()
        lines.extend(
            [
                f"{index}. [{outcome}] {entry.get('target_id')} / {entry.get('case_id')}",
                f"   Category: {entry.get('category')}",
                f"   Test: {entry.get('nodeid')}",
                f"   Rationale: {entry.get('rationale')}",
                "   Input:",
                _indent(_json(entry.get("input")), "     "),
            ]
        )
        if include_failure and entry.get("failure"):
            lines.extend(["   Failure excerpt:", _indent(_failure_excerpt(entry["failure"]), "     ")])
        lines.append("")

    if len(entries) > max_cases:
        lines.append(f"...and {len(entries) - max_cases} more case(s).")
    return "\n".join(lines).rstrip()


def format_test_report_markdown(
    report: dict[str, Any],
    *,
    failures_only: bool = True,
    max_cases: int = 25,
    include_failure: bool = False,
) -> str:
    summary = report.get("summary", {})
    entries = _selected_entries(report, failures_only=failures_only)
    shown = entries[:max_cases]
    lines = [
        "# LLM Fuzz CI Test Report",
        "",
        f"- Generated: `{report.get('generated_at', 'unknown')}`",
        f"- Executed cases: `{summary.get('executed_cases', 0)}`",
        f"- Passed cases: `{summary.get('passed_cases', 0)}`",
        f"- Failed cases: `{summary.get('failed_cases', 0)}`",
        "",
    ]
    if not shown:
        lines.append("No failed generated inputs found." if failures_only else "No generated inputs found.")
        return "\n".join(lines)

    heading = "Failing Inputs" if failures_only else "Generated Inputs"
    lines.extend([f"## {heading}", ""])
    for entry in shown:
        lines.extend(
            [
                f"### {entry.get('target_id')} / {entry.get('case_id')}",
                "",
                f"- Outcome: `{entry.get('outcome')}`",
                f"- Category: `{entry.get('category')}`",
                f"- Test: `{entry.get('nodeid')}`",
                f"- Rationale: {entry.get('rationale')}",
                "",
                "**Input**",
                "",
                _markdown_input(entry.get("input")),
                "",
            ]
        )
        if include_failure and entry.get("failure"):
            lines.extend(
                [
                    "Failure excerpt:",
                    "",
                    "```text",
                    _failure_excerpt(entry["failure"]),
                    "```",
                    "",
                ]
            )

    if len(entries) > max_cases:
        lines.append(f"_...and {len(entries) - max_cases} more case(s)._")
    return "\n".join(lines).rstrip()


def format_cases_markdown(
    cases: list[Any],
    *,
    max_cases: int = 100,
) -> str:
    shown = cases[:max_cases]
    lines = [
        "# LLM Fuzz CI Generated Inputs",
        "",
        f"- Generated inputs: `{len(cases)}`",
        "",
    ]
    if not shown:
        lines.append("No generated inputs found.")
        return "\n".join(lines)

    by_target: dict[str, list[Any]] = {}
    for case in shown:
        by_target.setdefault(str(case.target_id), []).append(case)

    for target_id, target_cases in by_target.items():
        lines.extend([f"## {target_id}", ""])
        for index, case in enumerate(target_cases, start=1):
            lines.extend(
                [
                    f"### Input {index}",
                    "",
                    f"- Category: `{case.category}`",
                    f"- Rationale: {case.rationale}",
                    "",
                    "**Input**",
                    "",
                    _markdown_input(case.input),
                    "",
                ]
            )

    if len(cases) > max_cases:
        lines.append(f"_...and {len(cases) - max_cases} more generated input(s)._")
    return "\n".join(lines).rstrip()


def format_full_report_markdown(
    *,
    cases: list[Any],
    test_report: dict[str, Any] | None = None,
    usage_report: dict[str, Any] | None = None,
    max_cases: int = 100,
    include_failure: bool = True,
) -> str:
    """Render one self-contained Markdown report for the CI artifact.

    Generated inputs and their test outcomes are merged so every input appears
    once, annotated with what happened to it. Failures come first.
    """
    entries = _merge_cases_and_results(cases, test_report)
    failures = [entry for entry in entries if entry["outcome"] == "failed"]

    lines = ["# LLM Fuzz CI Report", ""]
    lines.extend(_summary_section(entries, test_report, usage_report))
    lines.extend(_failures_section(failures, max_cases, include_failure))
    lines.extend(_inputs_section(entries, max_cases))
    lines.extend(_usage_section(usage_report))
    return "\n".join(lines).rstrip()


def _merge_cases_and_results(
    cases: list[Any],
    test_report: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    results = {
        str(entry.get("case_id")): entry
        for entry in _selected_entries(test_report or {}, failures_only=False)
    }

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        case_id = str(getattr(case, "id", ""))
        seen.add(case_id)
        result = results.get(case_id, {})
        entries.append(
            {
                "target_id": str(case.target_id),
                "case_id": case_id,
                "category": case.category,
                "rationale": case.rationale,
                "input": case.input,
                "outcome": str(result.get("outcome", "not tested")),
                "nodeid": result.get("nodeid"),
                "failure": result.get("failure"),
            }
        )

    # Results without a saved case should never happen, but a report that
    # silently drops them would hide exactly the corpus drift worth seeing.
    for case_id, result in results.items():
        if case_id in seen:
            continue
        entries.append(
            {
                "target_id": str(result.get("target_id", "unknown")),
                "case_id": case_id,
                "category": result.get("category"),
                "rationale": result.get("rationale"),
                "input": result.get("input"),
                "outcome": str(result.get("outcome", "unknown")),
                "nodeid": result.get("nodeid"),
                "failure": result.get("failure"),
            }
        )
    return entries


def _summary_section(
    entries: list[dict[str, Any]],
    test_report: dict[str, Any] | None,
    usage_report: dict[str, Any] | None,
) -> list[str]:
    counts = _outcome_counts(entries)
    rows = [("Generated inputs", str(len(entries)))]

    if test_report:
        rows.extend(
            [
                ("Tested inputs", str(counts["tested"])),
                ("Passed", str(counts["passed"])),
                ("Failed", str(counts["failed"])),
            ]
        )
        if counts["not tested"]:
            rows.append(("Not tested", str(counts["not tested"])))
        rows.append(("Report generated", str(test_report.get("generated_at", "unknown"))))

    if usage_report:
        rows.append(("Agent", str(usage_report.get("agent") or "unknown")))
        model = usage_report.get("model") or _usage_model(usage_report)
        if model:
            rows.append(("Model", str(model)))

    lines = ["## Summary", "", "| Metric | Value |", "| --- | --- |"]
    lines.extend(f"| {name} | `{value}` |" for name, value in rows)
    lines.extend(["", _verdict(counts, test_report), ""])
    return lines


def _verdict(counts: dict[str, int], test_report: dict[str, Any] | None) -> str:
    if test_report is None:
        return "No test results were recorded. This report covers generated inputs only."
    if counts["failed"]:
        return f"**{counts['failed']} generated input(s) failed a marked test.**"
    if int(test_report.get("exitstatus", 0)) != 0:
        return (
            "**The test run failed without recording a generated-input failure.** "
            "This usually means project setup failed, or a marked test had no "
            "generated inputs to run. Check the job log."
        )
    if counts["not tested"]:
        return (
            f"All tested inputs passed, but {counts['not tested']} generated input(s) "
            "were never run. Their `target_id` does not match any collected test."
        )
    if counts["tested"] == 0:
        return "No generated inputs were run."
    return "All generated inputs passed their marked tests."


def _failures_section(
    failures: list[dict[str, Any]],
    max_cases: int,
    include_failure: bool,
) -> list[str]:
    lines = ["## Failing Inputs", ""]
    if not failures:
        lines.extend(["No generated input failed its marked test.", ""])
        return lines

    for target_id, group in _group_by_target(failures[:max_cases]):
        lines.extend([f"### `{target_id}`", ""])
        for index, entry in enumerate(group, start=1):
            lines.extend(_case_block(entry, index, include_failure=include_failure))

    if len(failures) > max_cases:
        lines.extend([f"_...and {len(failures) - max_cases} more failing input(s)._", ""])
    return lines


def _inputs_section(entries: list[dict[str, Any]], max_cases: int) -> list[str]:
    lines = ["## All Generated Inputs", ""]
    if not entries:
        lines.extend(["No generated inputs found.", ""])
        return lines

    for target_id, group in _group_by_target(entries[:max_cases]):
        counts = _outcome_counts(group)
        lines.extend(
            [
                f"### `{target_id}`",
                "",
                f"{len(group)} input(s) — {counts['passed']} passed, "
                f"{counts['failed']} failed, {counts['not tested']} not tested.",
                "",
            ]
        )
        for index, entry in enumerate(group, start=1):
            lines.extend(_case_block(entry, index, include_failure=False))

    if len(entries) > max_cases:
        lines.extend([f"_...and {len(entries) - max_cases} more generated input(s)._", ""])
    return lines


def _case_block(
    entry: dict[str, Any],
    index: int,
    *,
    include_failure: bool,
) -> list[str]:
    lines = [
        f"#### Input {index} — `{entry.get('category')}` — `{entry['outcome']}`",
        "",
        _markdown_input(entry.get("input")),
        "",
    ]
    if entry.get("rationale"):
        lines.extend([f"Rationale: {entry['rationale']}", ""])
    if include_failure and entry.get("failure"):
        lines.extend(
            ["Failure excerpt:", "", "```text", _failure_excerpt(entry["failure"]), "```", ""]
        )
    return lines


def _usage_section(usage_report: dict[str, Any] | None) -> list[str]:
    usage = usage_report.get("usage") if usage_report else None
    if not isinstance(usage, dict):
        return []

    rows = [
        ("Input tokens", usage.get("input_tokens", 0)),
        ("Cached input tokens", usage.get("cached_input_tokens", 0)),
        ("Output tokens", usage.get("output_tokens", 0)),
        ("Reasoning output tokens", usage.get("reasoning_output_tokens", 0)),
        ("Total tokens", usage.get("total_tokens", 0)),
    ]
    lines = ["## Token Usage", "", "| Metric | Value |", "| --- | --- |"]
    lines.extend(f"| {name} | `{_thousands(value)}` |" for name, value in rows)
    lines.append("")
    return lines


def _group_by_target(
    entries: list[dict[str, Any]],
) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        grouped.setdefault(str(entry["target_id"]), []).append(entry)
    return list(grouped.items())


def _outcome_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"passed": 0, "failed": 0, "not tested": 0, "tested": 0}
    for entry in entries:
        outcome = entry["outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome != "not tested":
            counts["tested"] += 1
    return counts


def _usage_model(usage_report: dict[str, Any]) -> str | None:
    usage = usage_report.get("usage")
    return usage.get("model") if isinstance(usage, dict) else None


def _thousands(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def _selected_entries(
    report: dict[str, Any],
    *,
    failures_only: bool,
) -> list[dict[str, Any]]:
    key = "failures" if failures_only else "results"
    entries = report.get(key, [])
    return [entry for entry in entries if isinstance(entry, dict)]


def _json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _markdown_input(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return f"- value: {_markdown_value(value)}"
    return "\n".join(
        f"- `{_escape_markdown(str(key))}`: {_markdown_value(item)}"
        for key, item in value.items()
    )


def _markdown_value(value: Any) -> str:
    if isinstance(value, str):
        if "\n" in value or len(value) > 90:
            return _markdown_block(value, "text")
        return f"`{_escape_backticks(value)}`"
    if isinstance(value, (int, float, bool)) or value is None:
        return f"`{json.dumps(value, ensure_ascii=False)}`"
    return _markdown_block(_json(value), "json")


def _markdown_block(content: str, language: str, *, indent: str = "  ") -> str:
    """Render a fenced block that stays inside its Markdown list item.

    Every line carries the list continuation indent. Without it the first
    unindented line ends the list item, and the rest of the report is swallowed
    by the unclosed fence.
    """
    fence = _safe_fence(content)
    body = "\n".join(indent + line if line else line for line in content.splitlines())
    return f"\n\n{indent}{fence}{language}\n{body}\n{indent}{fence}"


def _safe_fence(content: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    return "`" * max(3, longest + 1)


def _escape_backticks(value: str) -> str:
    return value.replace("`", "\\`")


def _escape_markdown(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`")


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _failure_excerpt(text: str, *, max_lines: int = 12) -> str:
    lines = []
    for raw_line in strip_ansi(text).splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.lstrip().startswith(("E ", "E\t", ">")) or "AssertionError" in line:
            lines.append(line)
        elif re.search(r"\btests?/.*:\d+:", line):
            lines.append(line)
    if not lines:
        lines = [line for line in strip_ansi(text).splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)
