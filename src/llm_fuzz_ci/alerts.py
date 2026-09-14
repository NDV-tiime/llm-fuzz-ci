from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def report_has_failures(report: dict[str, Any]) -> bool:
    return bool(report.get("failures"))


def format_alert_body(report: dict[str, Any], *, max_failures: int = 10) -> str:
    summary = report.get("summary", {})
    lines = [
        "LLM Fuzz CI detected replay failures.",
        "",
        f"- Executed cases: {summary.get('executed_cases', 0)}",
        f"- Failed cases: {summary.get('failed_cases', 0)}",
        "",
        "Failing cases:",
    ]
    for failure in report.get("failures", [])[:max_failures]:
        lines.extend(
            [
                "",
                f"### {failure.get('target_id')} / {failure.get('case_id')}",
                f"- Node: `{failure.get('nodeid')}`",
                f"- Category: `{failure.get('category')}`",
                f"- Rationale: {failure.get('rationale')}",
                "",
                "Input:",
                "",
                "```json",
                json.dumps(failure.get("input"), indent=2, sort_keys=True, ensure_ascii=False),
                "```",
            ]
        )
    if len(report.get("failures", [])) > max_failures:
        lines.append("")
        lines.append(f"...and {len(report['failures']) - max_failures} more failures.")
    return "\n".join(lines)


def create_github_issue(
    *,
    report_path: str | Path,
    repo: str | None,
    token: str | None,
    title: str,
    labels: list[str],
    dry_run: bool = False,
) -> bool:
    report = load_report(report_path)
    if not report_has_failures(report):
        return False

    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    token = token or os.environ.get("GITHUB_TOKEN")
    if not repo:
        raise ValueError("GitHub repository is required, e.g. owner/name")
    if not token and not dry_run:
        raise ValueError("GitHub token is required")

    payload = {
        "title": title,
        "body": format_alert_body(report),
    }
    if labels:
        payload["labels"] = labels
    if dry_run:
        print(f"# {title}")
        print()
        print(f"Repository: {repo}")
        if labels:
            print(f"Labels: {', '.join(labels)}")
        print()
        print(payload["body"])
        return True

    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/issues",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            created = json.loads(response.read().decode("utf-8"))
            print(created.get("html_url", "GitHub issue created"))
            return True
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub issue creation failed: {exc.code} {body}") from exc
