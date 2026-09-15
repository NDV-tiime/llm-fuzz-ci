"""Command line entry point for LLM Fuzz CI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .generator import build_prompt, generate_cases
from .reports import SUMMARY_BYTES, render
from .schema import case_file, load_cases, load_targets, write_cases
from .usage import format_usage_summary, write_usage_report

TARGETS = ".llm-fuzz/targets.json"
CORPUS = ".llm-fuzz/cases"
TEST_REPORT = ".llm-fuzz/reports/test-report.json"
USAGE_REPORT = ".llm-fuzz/reports/llm-usage.json"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-fuzz-ci")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="Find pytest llm_fuzz targets")
    collect.add_argument("paths", nargs="*", default=["tests"])
    collect.add_argument("--output", default=TARGETS)
    collect.set_defaults(func=cmd_collect)

    generate = commands.add_parser("generate", help="Generate saved fuzz inputs")
    generate.add_argument("--targets", default=TARGETS)
    generate.add_argument("--corpus-dir", default=CORPUS)
    generate.add_argument("--agent", choices=["codex", "claude"], default="codex")
    generate.add_argument("--model", default=None)
    generate.add_argument(
        "--provider",
        default=None,
        help="Codex model provider id. Use 'openrouter' for the built-in shortcut.",
    )
    generate.add_argument(
        "--max-turns", type=int, default=None, help="Claude Code turns per target."
    )
    generate.add_argument(
        "--max-budget-usd",
        type=float,
        default=None,
        help="Override every marker budget. Enforced on Claude Code only.",
    )
    generate.add_argument("--timeout-seconds", type=int, default=600)
    generate.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent to the agent and exit, without spending.",
    )
    generate.add_argument("--show-usage", action="store_true")
    generate.add_argument("--usage-report", default=None)
    generate.set_defaults(func=cmd_generate)

    test = commands.add_parser("test-fuzz-cases", help="Run saved inputs with pytest")
    test.add_argument("--corpus-dir", default=CORPUS)
    test.add_argument("--report", default=TEST_REPORT)
    test.add_argument("--require-cases", action="store_true")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    test.set_defaults(func=cmd_test_fuzz_cases)

    summary = commands.add_parser("summary", help="Render the run as Markdown")
    summary.add_argument(
        "--format",
        choices=["full", "overview"],
        default="full",
        help="full: every input, for the artifact. overview: a digest, for CI.",
    )
    summary.add_argument("--corpus-dir", default=CORPUS)
    summary.add_argument("--report", default=TEST_REPORT)
    summary.add_argument("--usage-report", default=USAGE_REPORT)
    summary.add_argument("--output", default=".llm-fuzz/reports/llm-fuzz-ci-report.md")
    summary.set_defaults(func=cmd_summary)

    return parser


def cmd_collect(args: argparse.Namespace) -> int:
    import pytest

    status = pytest.main(
        [
            *plugin_args(),
            "--collect-only",
            "-q",
            f"--llm-fuzz-collect-targets={args.output}",
            *args.paths,
        ]
    )
    if status != 0:
        print(
            "\npytest could not collect those paths. If it could not import "
            "your code,\ninstall the project before running this, or set "
            "PYTHONPATH to where it lives.",
            file=sys.stderr,
        )
        return int(status)

    targets = load_targets(args.output)
    if not targets:
        # Silently collecting nothing is the most common first-run mistake, and
        # every later step would still be green.
        paths = " ".join(args.paths)
        print(
            f"No @pytest.mark.llm_fuzz tests found under {paths!r}.\n"
            "  - check the path is right\n"
            "  - check the test is marked: @pytest.mark.llm_fuzz\n"
            "  - check the marked test takes the llm_fuzz_case argument",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(targets)} marked test(s):")
    for target in targets:
        print(f"  {target.id}")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    targets = load_targets(args.targets)
    if args.dry_run:
        for target in targets:
            print(f"--- {target.id} " + "-" * max(0, 68 - len(target.id)))
            print(build_prompt(target, Path.cwd()))
        print(f"\n{len(targets)} agent run(s) would be made. Nothing was sent.")
        return 0
    print(
        f"Generating inputs for {len(targets)} target(s) with {args.agent}"
        f" — one agent run each.",
        flush=True,
    )
    result = generate_cases(
        targets,
        agent=args.agent,
        repo_root=Path.cwd(),
        model=args.model,
        provider=args.provider,
        max_turns=args.max_turns,
        max_budget_usd=args.max_budget_usd,
        timeout_seconds=args.timeout_seconds,
        capture_usage=args.show_usage or bool(args.usage_report),
    )

    dropped = clear_corpus(args.corpus_dir, targets)
    written = write_cases(args.corpus_dir, result.cases)
    written += mark_searched(args.corpus_dir, targets, result.cases)

    for path in dropped:
        print(f"Removed inputs for a test that no longer exists: {path.name}")

    print(f"Generated {len(result.cases)} input(s) across {len(written)} file(s).")
    for path in written:
        print(path)
    for reason in result.skipped:
        print(f"Discarded an unparseable input: {reason}")
    if args.show_usage:
        print(format_usage_summary(result.usage))
    if args.usage_report:
        path = write_usage_report(
            args.usage_report,
            agent=args.agent,
            model=args.model,
            provider=args.provider,
            target_count=len(targets),
            case_count=len(result.cases),
            usage=result.usage,
        )
        print(f"Wrote token usage to {path}.")
    return 0


def cmd_test_fuzz_cases(args: argparse.Namespace) -> int:
    import pytest

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    forwarded = list(args.pytest_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]

    options = [
        *plugin_args(),
        f"--llm-fuzz-corpus-dir={args.corpus_dir}",
        f"--llm-fuzz-report={args.report}",
    ]
    if args.require_cases:
        options.append("--llm-fuzz-require-cases")
    return pytest.main(options + (forwarded or ["tests"]))


def cmd_summary(args: argparse.Namespace) -> int:
    overview = args.format == "overview"
    content = render(
        cases=load_cases(args.corpus_dir),
        test_report=read_json(args.report),
        usage_report=read_json(args.usage_report),
        fold=overview,
        max_bytes=SUMMARY_BYTES if overview else None,
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content + "\n", encoding="utf-8")
    print(f"Wrote {path}.")
    return 0


def mark_searched(corpus_dir: str | Path, targets: list[Any], cases: list[Any]) -> list[Path]:
    """Leave an empty file for a target the agent found no weakness in.

    Without it the test run cannot tell "the agent looked and found nothing"
    from "generation never happened", and would fail the build for both.
    """
    covered = {case.target_id for case in cases}
    empty = []
    for target in targets:
        if target.id in covered:
            continue
        path = case_file(corpus_dir, target.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        empty.append(path)
    return empty


def clear_corpus(corpus_dir: str | Path, targets: list[Any]) -> list[Path]:
    """Empty the corpus before regenerating it.

    Files for the current targets are replaced. Files for targets that no
    longer exist are deleted, or a renamed test leaves inputs behind that every
    later run reports as `not tested`.
    """
    root = Path(corpus_dir)
    if not root.exists():
        return []
    keep = {case_file(root, target.id) for target in targets}
    stale = []
    for path in sorted(root.glob("*.jsonl")):
        path.unlink()
        if path not in keep:
            stale.append(path)
    return stale


def plugin_args() -> list[str]:
    """Load the plugin once, by module, whether or not it is pip-installed."""
    return ["-p", "no:llm_fuzz_ci", "-p", "llm_fuzz_ci.pytest_plugin"]


def read_json(path: str | Path) -> dict[str, Any] | None:
    file = Path(path)
    return json.loads(file.read_text(encoding="utf-8")) if file.exists() else None


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
