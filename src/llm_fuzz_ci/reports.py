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
                f"   Test: {entry.get('nodeid')}",
                f"   Why this input: {entry.get('rationale')}",
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
                f"- Test: `{entry.get('nodeid')}`",
                f"- Why this input: {entry.get('rationale')}",
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
                    f"- Why this input: {case.rationale}",
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


OVERVIEW_VALUE_CHARS = 220
ARTIFACT_POINTER = (
    "Every input, in full, is in the `llm-fuzz-ci-report` artifact "
    "(`llm-fuzz-ci-report.md`)."
)


def format_overview_markdown(
    *,
    cases: list[Any],
    test_report: dict[str, Any] | None = None,
    usage_report: dict[str, Any] | None = None,
    inputs_per_target: int = 25,
    max_inputs: int = 200,
    max_failures: int = 10,
) -> str:
    """Render the short Markdown shown in the GitHub Actions run summary.

    This is a glance surface: one verdict, one table, failures in full, and
    everything else folded away. The exhaustive listing belongs in the
    artifact, not in a log page nobody can scroll.
    """
    entries = _merge_cases_and_results(cases, test_report)
    failures = [entry for entry in entries if entry["outcome"] == "failed"]
    counts = _outcome_counts(entries)
    groups = _group_by_target(entries)

    lines = [_overview_heading(counts, test_report), ""]
    if not entries:
        lines.extend(["No generated inputs were found.", "", ARTIFACT_POINTER])
        return "\n".join(lines)

    lines.extend(_overview_subtitle(entries, groups, usage_report))
    lines.extend(_overview_table(groups, test_report))

    if failures:
        lines.extend(["### Failures", ""])
        for entry in failures[:max_failures]:
            lines.extend(_overview_case(entry, include_failure=True))
        if len(failures) > max_failures:
            lines.extend([f"_...and {len(failures) - max_failures} more._", ""])

    lines.extend(_overview_by_target(groups, inputs_per_target, max_inputs))
    lines.extend([ARTIFACT_POINTER, ""])
    return "\n".join(lines).rstrip()


def _overview_heading(counts: dict[str, int], test_report: dict[str, Any] | None) -> str:
    if test_report is None:
        return "## LLM Fuzz CI — generated inputs"
    if counts["failed"]:
        return (
            f"## LLM Fuzz CI — {counts['failed']} of {counts['tested']} "
            "tested inputs failed"
        )
    if int(test_report.get("exitstatus", 0)) != 0:
        return "## LLM Fuzz CI — the test run failed before any input was judged"
    return f"## LLM Fuzz CI — all {counts['tested']} tested inputs passed"


def _overview_subtitle(
    entries: list[dict[str, Any]],
    groups: list[tuple[str, list[dict[str, Any]]]],
    usage_report: dict[str, Any] | None,
) -> list[str]:
    parts = [f"**{len(entries)}** inputs across **{len(groups)}** targets"]
    if usage_report:
        agent = usage_report.get("agent")
        model = usage_report.get("model") or _usage_model(usage_report)
        if agent:
            parts.append(f"`{agent}`" + (f" `{model}`" if model else ""))
        usage = usage_report.get("usage")
        if isinstance(usage, dict) and usage.get("total_tokens"):
            parts.append(f"{_thousands(usage['total_tokens'])} tokens")
    return [" · ".join(parts), ""]


def _overview_table(
    groups: list[tuple[str, list[dict[str, Any]]]],
    test_report: dict[str, Any] | None,
) -> list[str]:
    if test_report is None:
        lines = ["| Target | Inputs |", "| --- | --: |"]
        for target_id, group in groups:
            lines.append(f"| `{_short_target(target_id)}` | {len(group)} |")
        return lines + [""]

    untested = any(entry["outcome"] == "not tested" for _, g in groups for entry in g)
    header = "| Target | Inputs | Passed | Failed |"
    divider = "| --- | --: | --: | --: |"
    if untested:
        header += " Not tested |"
        divider += " --: |"

    lines = [header, divider]
    for target_id, group in groups:
        counts = _outcome_counts(group)
        row = (
            f"| `{_short_target(target_id)}` | {len(group)} "
            f"| {counts['passed']} | {counts['failed']} |"
        )
        if untested:
            row += f" {counts['not tested']} |"
        lines.append(row)
    return lines + [""]


def _overview_by_target(
    groups: list[tuple[str, list[dict[str, Any]]]],
    inputs_per_target: int,
    max_inputs: int,
) -> list[str]:
    """One collapsed section per marked test, holding all of its inputs.

    Collapsed, each marked test costs the reader a single line, so a repository
    with fifty markers still renders a list you can take in at once. Every
    marked test gets its section and tally; only the listing inside is dropped
    once the whole digest would outgrow the run summary.
    """
    lines = ["### Inputs by test", ""]
    budget = max_inputs
    for target_id, group in groups:
        shown = group[: min(inputs_per_target, budget)]
        budget -= len(shown)
        lines.extend(
            [
                "<details>",
                f"<summary><code>{_html_escape(_short_target(target_id))}</code>"
                f" — {_group_tally(group)}</summary>",
                "",
            ]
        )
        for index, entry in enumerate(shown, start=1):
            lines.extend(_overview_case(entry, index=index))
        if len(group) > len(shown):
            lines.extend(
                [
                    f"_{len(group) - len(shown)} more input(s) — see the "
                    "`llm-fuzz-ci-report` artifact._",
                    "",
                ]
            )
        lines.extend(["</details>", ""])
    return lines


def _group_tally(group: list[dict[str, Any]]) -> str:
    counts = _outcome_counts(group)
    parts = [f"{len(group)} input(s)"]
    for name in ("passed", "failed", "not tested"):
        if counts[name]:
            parts.append(f"{counts[name]} {name}")
    return " · ".join(parts)


def _overview_case(
    entry: dict[str, Any],
    *,
    index: int | None = None,
    include_failure: bool = False,
) -> list[str]:
    metadata = f"`{entry['outcome']}`"
    if index is not None:
        label = f"**{index}.** {metadata}"
    else:
        label = f"**`{_short_target(entry['target_id'])}`** — {metadata}"
    lines = [label, ""]
    if entry.get("rationale"):
        lines.extend([str(entry["rationale"]), ""])
    lines.extend(_compact_input_block(entry.get("input")))
    if include_failure and entry.get("failure"):
        lines.extend(
            ["```text", _failure_excerpt(entry["failure"], max_lines=6), "```", ""]
        )
    return lines


def _html_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _compact_input_block(value: Any) -> list[str]:
    """Render the whole input as one top-level fenced block.

    Top level, not nested in a list: an over-long payload can then never break
    out of its container and eat the rest of the page.
    """
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(rendered) > OVERVIEW_VALUE_CHARS:
        rendered = rendered[:OVERVIEW_VALUE_CHARS] + f"… (+{len(rendered) - OVERVIEW_VALUE_CHARS:,} chars)"
    fence = _safe_fence(rendered)
    return [f"{fence}json", rendered, fence, ""]


def _short_target(target_id: str) -> str:
    return str(target_id).rsplit("::", 1)[-1]



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
        f"#### Input {index} — `{entry['outcome']}`",
        "",
        _markdown_input(entry.get("input")),
        "",
    ]
    if entry.get("rationale"):
        lines.extend([f"Why this input: {entry['rationale']}", ""])
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
