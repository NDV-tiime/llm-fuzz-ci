import json
import subprocess

import pytest

from llm_fuzz_ci import vitest_runner
from llm_fuzz_ci.cli import resolve_runner
from llm_fuzz_ci.schema import stable_case_id


def test_javascript_paths_pick_vitest_without_being_told():
    assert resolve_runner("auto", ["tests/redirect.fuzz.test.mjs"]) == "vitest"
    assert resolve_runner("auto", ["src/a.ts", "src/b.tsx"]) == "vitest"


def test_python_paths_stay_on_pytest():
    assert resolve_runner("auto", ["tests/test_app.py"]) == "pytest"
    assert resolve_runner("auto", []) == "pytest"


def test_an_explicit_runner_wins_over_the_extension():
    assert resolve_runner("pytest", ["tests/a.test.ts"]) == "pytest"
    assert resolve_runner("vitest", ["tests/test_app.py"]) == "vitest"


def test_a_project_local_vitest_is_preferred(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "node_modules" / ".bin" / "vitest").write_text("#!/bin/sh\n")

    assert vitest_runner.vitest_command(["tests"])[0].endswith("node_modules/.bin/vitest")


def test_npx_is_the_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert vitest_runner.vitest_command(["tests"])[:2] == ["npx", "--no-install"]


def test_the_case_id_is_derived_here_so_the_two_runners_agree(tmp_path):
    """The JS helper deliberately sends no case_id.

    It is a hash of the input, and a second implementation of it in JavaScript
    would drift from this one without anything failing loudly.
    """
    target = "tests/a.test.mjs::rejects a bad url"
    report = tmp_path / "test-report.json"

    vitest_runner.write_report(
        str(report),
        [{"target_id": target, "input": {"url": "//evil"}, "outcome": "failed"}],
        exitstatus=1,
    )

    written = json.loads(report.read_text(encoding="utf-8"))
    assert written["results"][0]["case_id"] == stable_case_id(target, {"url": "//evil"})
    assert written["summary"] == {
        "executed_cases": 1,
        "failed_cases": 1,
        "passed_cases": 0,
    }


def test_records_the_helper_wrote_are_read_back_whole(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"outcome": "passed"}))
    (tmp_path / "b.json").write_text("{ not json")

    assert vitest_runner.drain(tmp_path) == [{"outcome": "passed"}]


def test_a_missing_directory_is_no_results_rather_than_a_crash(tmp_path):
    assert vitest_runner.drain(tmp_path / "nothing-here") == []


def test_collection_asks_vitest_to_list_rather_than_run(tmp_path, monkeypatch):
    """Pointing collect at a directory must not execute the tests in it."""
    monkeypatch.chdir(tmp_path)

    assert vitest_runner.vitest_command(["tests"], "list")[-2:] == ["list", "tests"]
    assert "run" not in vitest_runner.vitest_command(["tests"], "list")
    assert "run" in vitest_runner.vitest_command(["tests"])


def test_a_missing_vitest_is_named_rather_than_left_to_npm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vitest_runner.shutil, "which", lambda name: "/usr/bin/npx")
    monkeypatch.setattr(
        vitest_runner.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, b"", b"npm error ..."),
    )

    with pytest.raises(RuntimeError, match="npm install --save-dev vitest"):
        vitest_runner.require_vitest()


def test_a_project_local_vitest_needs_no_probe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "node_modules" / ".bin" / "vitest").write_text("#!/bin/sh\n")

    def explode(*a, **k):
        raise AssertionError("should not have shelled out")

    monkeypatch.setattr(vitest_runner.subprocess, "run", explode)
    vitest_runner.require_vitest()


def test_a_clean_run_that_registered_nothing_still_tries_the_other_mode(tmp_path, monkeypatch):
    """`vitest list` exiting 0 with no targets is the case that hid a CI failure."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(vitest_runner, "require_vitest", lambda: None)
    modes = []

    def fake_run(cmd, **kwargs):
        modes.append("list" if "list" in cmd else "run")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(vitest_runner.subprocess, "run", fake_run)
    vitest_runner.collect(["tests"], str(tmp_path / "targets.json"))

    assert modes == ["list", "run"]
