from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .alerts import create_github_issue, load_report
from .generator import generate_cases_with_usage
from .reports import (
    format_cases_markdown,
    format_test_report_markdown,
    format_test_report_text,
)
from .schema import case_file, load_cases, load_targets, write_cases
from .usage import format_usage_summary, write_usage_report


def _pytest_plugin_args() -> list[str]:
    return ["-p", "no:llm_fuzz_ci", "-p", "llm_fuzz_ci.pytest_plugin"]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-fuzz-ci")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect pytest llm_fuzz targets")
    collect.add_argument("paths", nargs="*", default=["tests"])
    collect.add_argument("--output", default=".llm-fuzz/targets.json")
    collect.set_defaults(func=cmd_collect)

    generate = subparsers.add_parser("generate", help="Generate saved fuzz cases")
    generate.add_argument("--targets", default=".llm-fuzz/targets.json")
    generate.add_argument("--corpus-dir", default=".llm-fuzz/cases")
    generate.add_argument(
        "--agent",
        choices=["codex", "claude"],
        default="codex",
        help="Coding agent used to generate cases.",
    )
    generate.add_argument("--model", default=None)
    generate.add_argument(
        "--provider",
        default=None,
        help=(
            "Optional Codex model provider id. Use 'openrouter' for the built-in "
            "OpenRouter shortcut, or any provider id configured in Codex."
        ),
    )
    generate.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Optional override for the maximum generated cases per target.",
    )
    generate.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Optional maximum Claude Code turns per target.",
    )
    generate.add_argument(
        "--max-budget-usd",
        type=float,
        default=None,
        help=(
            "Optional override for every target's required marker budget. "
            "Claude Code receives this as --max-budget-usd per target."
        ),
    )
    generate.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Maximum agent generation time per target.",
    )
    generate.add_argument(
        "--show-usage",
        action="store_true",
        help="Print total LLM token usage emitted by the selected agent.",
    )
    generate.add_argument(
        "--usage-report",
        default=None,
        help="Optional path where LLM token usage metadata is written as JSON.",
    )
    generate.set_defaults(func=cmd_generate)

    test_fuzz_cases = subparsers.add_parser(
        "test-fuzz-cases",
        help="Test generated fuzz cases with pytest",
    )
    test_fuzz_cases.add_argument("--corpus-dir", default=".llm-fuzz/cases")
    test_fuzz_cases.add_argument("--report", default=".llm-fuzz/reports/test-report.json")
    test_fuzz_cases.add_argument("--require-cases", action="store_true")
    test_fuzz_cases.add_argument("pytest_args", nargs=argparse.REMAINDER)
    test_fuzz_cases.set_defaults(func=cmd_test_fuzz_cases)

    cases = subparsers.add_parser("cases", help="Render generated fuzz cases")
    cases.add_argument("--corpus-dir", default=".llm-fuzz/cases")
    cases.add_argument(
        "--format",
        choices=["markdown"],
        default="markdown",
        help="Output format for generated cases.",
    )
    cases.add_argument("--output", default=None, help="Optional file to write.")
    cases.add_argument("--max-cases", type=int, default=100)
    cases.set_defaults(func=cmd_cases)

    report = subparsers.add_parser("report", help="Render a test report")
    report.add_argument("--report", default=".llm-fuzz/reports/test-report.json")
    report.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Output format for the rendered report.",
    )
    report.add_argument("--output", default=None, help="Optional file to write.")
    report.add_argument(
        "--all",
        action="store_true",
        help="Show passed and failed cases. By default only failures are shown.",
    )
    report.add_argument("--max-cases", type=int, default=25)
    report.add_argument(
        "--show-failure-details",
        action="store_true",
        help="Include compact pytest failure excerpts.",
    )
    report.set_defaults(func=cmd_report)

    alert = subparsers.add_parser("alert", help="Send alerts for a test report")
    alert_subparsers = alert.add_subparsers(dest="alert_command", required=True)

    github_issue = alert_subparsers.add_parser("github-issue")
    github_issue.add_argument("--report", default=".llm-fuzz/reports/test-report.json")
    github_issue.add_argument("--repo", default=None)
    github_issue.add_argument("--token", default=None)
    github_issue.add_argument("--title", default="LLM Fuzz CI detected a vulnerability")
    github_issue.add_argument("--label", action="append", default=[])
    github_issue.add_argument("--dry-run", action="store_true")
    github_issue.set_defaults(func=cmd_alert_github_issue)

    return parser


def cmd_collect(args: argparse.Namespace) -> int:
    import pytest

    pytest_args = [
        *_pytest_plugin_args(),
        "--collect-only",
        "-q",
        f"--llm-fuzz-collect-targets={args.output}",
        *args.paths,
    ]
    return pytest.main(pytest_args)


def cmd_generate(args: argparse.Namespace) -> int:
    repo_root = Path.cwd()
    targets = load_targets(args.targets)
    result = generate_cases_with_usage(
        targets,
        agent=args.agent,
        repo_root=repo_root,
        model=args.model,
        provider=args.provider,
        max_cases=args.max_cases,
        max_turns=args.max_turns,
        max_budget_usd=args.max_budget_usd,
        timeout_seconds=args.timeout_seconds,
        capture_usage=args.show_usage or bool(args.usage_report),
    )
    cases = result.cases
    for target in targets:
        existing_path = case_file(args.corpus_dir, target.id)
        if existing_path.exists():
            existing_path.unlink()
    written = write_cases(args.corpus_dir, cases, merge=False)
    print(f"Generated {len(cases)} fuzz case(s) across {len(written)} file(s).")
    for path in written:
        print(path)
    if args.show_usage:
        print(format_usage_summary(result.usage))
    if args.usage_report:
        path = write_usage_report(
            args.usage_report,
            agent=args.agent,
            model=args.model,
            provider=args.provider,
            target_count=len(targets),
            case_count=len(cases),
            usage=result.usage,
        )
        print(f"Wrote LLM token usage report to {path}.")
    return 0


def cmd_test_fuzz_cases(args: argparse.Namespace) -> int:
    import pytest

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = ["tests"]
    pytest_args = [
        *_pytest_plugin_args(),
        f"--llm-fuzz-corpus-dir={args.corpus_dir}",
        f"--llm-fuzz-report={args.report}",
        *pytest_args,
    ]
    if args.require_cases:
        pytest_args.insert(4, "--llm-fuzz-require-cases")
    return pytest.main(pytest_args)


def cmd_cases(args: argparse.Namespace) -> int:
    content = format_cases_markdown(
        load_cases(args.corpus_dir),
        max_cases=args.max_cases,
    )
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
        print(f"Wrote generated inputs report to {path}.")
    else:
        print(content)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    report = load_report(args.report)
    if args.format == "json":
        content = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    elif args.format == "markdown":
        content = format_test_report_markdown(
            report,
            failures_only=not args.all,
            max_cases=args.max_cases,
            include_failure=args.show_failure_details,
        )
    else:
        content = format_test_report_text(
            report,
            failures_only=not args.all,
            max_cases=args.max_cases,
            include_failure=args.show_failure_details,
        )

    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content + "\n", encoding="utf-8")
        print(f"Wrote rendered test report to {path}.")
    else:
        print(content)
    return 0


def cmd_alert_github_issue(args: argparse.Namespace) -> int:
    created = create_github_issue(
        report_path=args.report,
        repo=args.repo,
        token=args.token,
        title=args.title,
        labels=args.label,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print("Alert dry run rendered." if created else "No failures found; no alert sent.")
    else:
        print("Alert created." if created else "No failures found; no alert sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
