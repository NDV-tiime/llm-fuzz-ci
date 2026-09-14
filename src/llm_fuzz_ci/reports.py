from __future__ import annotations

import json
import re
from typing import Any


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def format_replay_report_text(
    report: dict[str, Any],
    *,
    failures_only: bool = True,
    max_cases: int = 25,
    include_failure: bool = False,
) -> str:
    summary = report.get("summary", {})
    entries = _selected_entries(report, failures_only=failures_only)
    shown = entries[:max_cases]
    title = "LLM Fuzz CI Replay Report"
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
        lines.append("No failed fuzz cases found." if failures_only else "No fuzz cases found.")
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


def format_replay_report_markdown(
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
        "# LLM Fuzz CI Replay Report",
        "",
        f"- Generated: `{report.get('generated_at', 'unknown')}`",
        f"- Executed cases: `{summary.get('executed_cases', 0)}`",
        f"- Passed cases: `{summary.get('passed_cases', 0)}`",
        f"- Failed cases: `{summary.get('failed_cases', 0)}`",
        "",
    ]
    if not shown:
        lines.append("No failed fuzz cases found." if failures_only else "No fuzz cases found.")
        return "\n".join(lines)

    heading = "Failing Cases" if failures_only else "Cases"
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
                "Input:",
                "",
                "```json",
                _json(entry.get("input")),
                "```",
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
