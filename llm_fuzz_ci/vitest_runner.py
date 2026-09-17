"""Run vitest the way the pytest plugin runs pytest.

The JS helper knows only how to describe one target and record one result. The
shapes on disk -- targets.json, test-report.json -- stay defined here, so both
runners produce a run the rest of the tool cannot tell apart.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .schema import (
    REPORT_SCHEMA_VERSION,
    FuzzTarget,
    stable_case_id,
    utc_now,
    write_targets,
)


def vitest_command(paths: list[str], mode: str = "run") -> list[str]:
    """Prefer a project-local vitest; fall back to whatever npx resolves."""
    local = Path("node_modules/.bin/vitest")
    base = [str(local)] if local.exists() else ["npx", "--no-install", "vitest"]
    if mode == "list":
        return [*base, "list", *paths]
    return [*base, "run", "--reporter=dot", *paths]


def drain(directory: Path) -> list[dict[str, Any]]:
    """Every record the helper wrote.

    The order is arbitrary -- the filenames are uuids, and vitest writes them
    from parallel workers. Nothing downstream depends on it: the report walks
    the corpus and looks each result up by id.
    """
    if not directory.exists():
        return []
    records = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except ValueError:
            continue
    return records


MISSING_VITEST = (
    "vitest was not found in this project. Install it before running this:\n"
    "  npm install --save-dev vitest\n"
    "Without it npm answers with its own error, which says nothing about fuzzing."
)


def require_vitest() -> None:
    """Fail with one clear line rather than letting npm explain itself."""
    if Path("node_modules/.bin/vitest").exists():
        return
    if shutil.which("npx") is None:
        raise RuntimeError(MISSING_VITEST)
    probe = subprocess.run(
        ["npx", "--no-install", "vitest", "--version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        raise RuntimeError(MISSING_VITEST)


def collect(paths: list[str], output: str) -> int:
    """Discover fuzzTest targets and write them where `generate` looks.

    `vitest list` imports the test files without running them, which is what
    collection has to mean: pointing this at a directory must not execute the
    ordinary tests that live there. Older vitest has no `list`, so a run is the
    fallback -- and there the helper's own skip is all that holds tests back.
    """
    require_vitest()
    for mode in ("list", "run"):
        with tempfile.TemporaryDirectory(prefix="llm-fuzz-collect-") as tmp:
            env = os.environ.copy()
            env["LLM_FUZZ_COLLECT_DIR"] = tmp
            completed = subprocess.run(
                vitest_command(paths, mode), env=env, check=False
            )
            targets = [FuzzTarget.from_dict(item) for item in drain(Path(tmp))]
        if targets or completed.returncode == 0:
            break

    if completed.returncode != 0 and not targets:
        return completed.returncode
    write_targets(output, sorted(targets, key=lambda target: target.id))
    return 0


def run_cases(
    paths: list[str],
    *,
    corpus_dir: str,
    report: str,
    require_cases: bool,
) -> int:
    """Replay every saved input and write the report the summary reads."""
    require_vitest()
    with tempfile.TemporaryDirectory(prefix="llm-fuzz-results-") as tmp:
        env = os.environ.copy()
        env["LLM_FUZZ_RESULT_DIR"] = tmp
        env["LLM_FUZZ_CORPUS_DIR"] = corpus_dir
        if require_cases:
            env["LLM_FUZZ_REQUIRE_CASES"] = "1"
        completed = subprocess.run(vitest_command(paths), env=env, check=False)
        results = drain(Path(tmp))

    write_report(report, results, completed.returncode)
    return completed.returncode


def write_report(path: str, results: list[dict[str, Any]], exitstatus: int) -> Path:
    for item in results:
        item.setdefault(
            "case_id", stable_case_id(item.get("target_id", ""), item.get("input"))
        )
    failed = [item for item in results if item.get("outcome") == "failed"]
    payload = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": utc_now(),
        "exitstatus": exitstatus,
        "summary": {
            "executed_cases": len(results),
            "failed_cases": len(failed),
            "passed_cases": sum(1 for r in results if r.get("outcome") == "passed"),
        },
        "results": results,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output
