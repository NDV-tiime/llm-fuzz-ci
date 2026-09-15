"""Render a fuzz run as one Markdown document."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# GitHub discards a step summary over 1 MiB and annotates the run with an error.
SUMMARY_BYTES = 900_000

ARTIFACT_HINT = (
    "Every input, in full, is in the `llm-fuzz-ci-report` artifact "
    "(`llm-fuzz-ci-report.md`)."
)

OUTCOME_ORDER = ["passed", "failed", "invalid input", "skipped", "not tested"]


@dataclass
class Budget:
    """Byte allowance for a document.

    Inputs are dropped whole: a payload is shown complete or counted as
    omitted, never cut in half.
    """

    remaining: int | None

    def take(self, lines: list[str]) -> bool:
        if self.remaining is None:
            return True
        cost = sum(len(line) + 1 for line in lines)
        if cost > self.remaining:
            return False
        self.remaining -= cost
        return True


def render(
    *,
    cases: list[Any],
    test_report: dict[str, Any] | None = None,
    usage_report: dict[str, Any] | None = None,
    fold: bool = False,
    max_bytes: int | None = None,
) -> str:
    """Render one run.

    `fold` hides each test's inputs behind a collapsed section and `max_bytes`
    caps the total; that pair is what the GitHub Actions run summary wants.
    The downloadable artifact wants neither.
    """
    entries = merge(cases, test_report)
    if not entries:
        return "# LLM Fuzz CI\n\nNo generated inputs were found."

    budget = Budget(max_bytes)
    failures = [entry for entry in entries if entry["outcome"] == "failed"]
    lines = ["# LLM Fuzz CI", ""]
    lines += target_table(entries)
    lines += run_facts(test_report, usage_report)
    lines += [verdict(entries, test_report), ""]
    lines += failures_section(failures, budget)
    lines += inputs_section(by_target(entries), fold, budget)
    if fold:
        lines.append(ARTIFACT_HINT)
    return "\n".join(lines).rstrip()


def merge(cases: list[Any], test_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Pair every generated input with what the test run did to it."""
    results = {
        str(item.get("case_id")): item
        for item in (test_report or {}).get("results", [])
        if isinstance(item, dict)
    }
    entries = [
        {
            "target_id": str(case.target_id),
            "input": case.input,
            "rationale": case.rationale,
            "outcome": str(results.get(case.id, {}).get("outcome", "not tested")),
            "failure": results.get(case.id, {}).get("failure"),
        }
        for case in cases
    ]
    # A result with no saved case means the corpus and the run disagree. Showing
    # it is the only way that ever becomes visible.
    known = {case.id for case in cases}
    entries += [
        {
            "target_id": str(item.get("target_id", "unknown")),
            "input": item.get("input"),
            "rationale": item.get("rationale"),
            "outcome": str(item.get("outcome", "unknown")),
            "failure": item.get("failure"),
        }
        for case_id, item in results.items()
        if case_id not in known
    ]
    return entries


def by_target(entries: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(entry["target_id"], []).append(entry)
    return list(groups.items())


def tally(entries: list[dict[str, Any]]) -> dict[str, int]:
    """Count entries by outcome, keeping whatever pytest reported."""
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["outcome"]] = counts.get(entry["outcome"], 0) + 1
    return counts


def outcomes(entries: list[dict[str, Any]]) -> str:
    """Compact tally, for example `7 passed · 1 failed`."""
    counts = tally(entries)
    listed = [f"{counts[name]} {name}" for name in OUTCOME_ORDER if counts.get(name)]
    rest = [f"{n} {name}" for name, n in counts.items() if name not in OUTCOME_ORDER]
    return " · ".join(listed + rest) or "—"


def target_table(entries: list[dict[str, Any]]) -> list[str]:
    lines = ["| Test | Inputs | Outcome |", "| --- | --: | --- |"]
    lines += [
        f"| `{short_target(target_id)}` | {len(group)} | {outcomes(group)} |"
        for target_id, group in by_target(entries)
    ]
    return lines + [""]


def run_facts(
    test_report: dict[str, Any] | None,
    usage_report: dict[str, Any] | None,
) -> list[str]:
    facts = []
    if test_report:
        facts.append(f"Run `{test_report.get('generated_at', 'unknown')}`")
    if usage_report:
        agent, model = usage_report.get("agent"), usage_report.get("model")
        if agent:
            facts.append(f"`{agent}`" + (f" `{model}`" if model else ""))
        usage = usage_report.get("usage")
        if isinstance(usage, dict) and usage.get("total_tokens"):
            facts.append(f"{usage['total_tokens']:,} tokens")
    return [" · ".join(facts), ""] if facts else []


def verdict(entries: list[dict[str, Any]], test_report: dict[str, Any] | None) -> str:
    if test_report is None:
        return "No test results yet. This covers generated inputs only."

    counts = tally(entries)
    failed = counts.get("failed", 0)
    skipped = counts.get("skipped", 0)
    invalid = counts.get("invalid input", 0)
    untested = counts.get("not tested", 0)
    ran = len(entries) - untested
    note = (
        f" {invalid} input(s) did not match the function signature and were not judged."
        if invalid
        else ""
    )

    if failed:
        return f"**{failed} of {ran} tested inputs failed.**{note}"
    if invalid:
        # pytest exits non-zero for these, so explain them before falling
        # through to the generic "something went wrong" message below.
        return (
            f"No generated input failed.{note} "
            "Read those keys off `llm_fuzz_case.input` by name to avoid it."
        )
    if int(test_report.get("exitstatus", 0)) != 0:
        return (
            "**The run failed without recording a generated-input failure.** "
            "Project setup failed, or a marked test had no inputs to run."
        )
    if untested:
        return (
            f"{ran} tested inputs passed, but {untested} never ran: "
            "their target matches no collected test."
        )
    if not ran:
        return "No generated inputs ran."
    if skipped:
        return f"{ran - skipped} tested inputs passed, {skipped} skipped."
    return f"All {ran} tested inputs passed."


def failures_section(failures: list[dict[str, Any]], budget: Budget) -> list[str]:
    if not failures:
        return []
    lines = ["## Failures", ""]
    shown = 0
    for entry in failures:
        block = failure_block(entry)
        if not budget.take(block):
            break
        lines += block
        shown += 1
    return lines + omitted(len(failures) - shown)


def inputs_section(
    groups: list[tuple[str, list[dict[str, Any]]]],
    fold: bool,
    budget: Budget,
) -> list[str]:
    lines = ["## Inputs by test", ""]
    for target_id, group in groups:
        blocks: list[str] = []
        shown = 0
        for entry in group:
            block = case_block(entry, shown + 1)
            if not budget.take(block):
                break
            blocks += block
            shown += 1
        name = short_target(target_id)
        if fold:
            lines += [
                "<details>",
                f"<summary><code>{escape_html(name)}</code> — {outcomes(group)}</summary>",
                "",
            ]
        else:
            lines += [f"### `{name}` — {outcomes(group)}", ""]
        lines += blocks + omitted(len(group) - shown)
        if fold:
            lines += ["</details>", ""]
    return lines


def omitted(count: int) -> list[str]:
    return [f"_{count} more — see the artifact._", ""] if count > 0 else []


def case_block(entry: dict[str, Any], index: int) -> list[str]:
    """One input, with its outcome. Failures carry their excerpt above."""
    lines = [f"**{index}.** `{entry['outcome']}`", ""]
    if entry.get("rationale"):
        lines += [str(entry["rationale"]), ""]
    return lines + input_block(entry.get("input"))


def failure_block(entry: dict[str, Any]) -> list[str]:
    lines = [f"**`{short_target(entry['target_id'])}`**", ""]
    if entry.get("rationale"):
        lines += [str(entry["rationale"]), ""]
    lines += input_block(entry.get("input"))
    if entry.get("failure"):
        lines += code_block(failure_excerpt(entry["failure"]), "text")
    return lines


def input_block(value: Any) -> list[str]:
    return code_block(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), "json"
    )


def code_block(content: str, language: str) -> list[str]:
    """Fence `content` with a fence longer than any backtick run inside it."""
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    marks = "`" * max(3, longest + 1)
    return [f"{marks}{language}", content, marks, ""]


def failure_excerpt(text: str, max_lines: int = 12) -> str:
    """Keep the assertion and location lines out of a pytest traceback."""
    clean = ANSI.sub("", text)
    keep = [
        line.rstrip()
        for line in clean.splitlines()
        if line.strip()
        and (
            line.lstrip().startswith(("E ", "E\t", ">"))
            or "AssertionError" in line
            or re.search(r"\btests?/.*:\d+:", line)
        )
    ]
    return "\n".join((keep or [l for l in clean.splitlines() if l.strip()])[:max_lines])


def short_target(target_id: str) -> str:
    """The test name, without the file path pytest prefixes it with."""
    return str(target_id).rsplit("::", 1)[-1]


def escape_html(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
