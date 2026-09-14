from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from importlib.resources import files
from pathlib import Path
from typing import Iterable

from .schema import AGENT_OUTPUT_SCHEMA, FuzzCase, FuzzTarget
from .usage import LLMUsage, extract_usage_from_json_events

CLAUDE_INSPECT_TOOLS = "Read,Grep,Glob,Bash"
CLAUDE_ALLOWED_INSPECT_TOOLS = [
    "Read",
    "Grep",
    "Glob",
    "Bash(pwd)",
    "Bash(ls *)",
    "Bash(rg *)",
    "Bash(git diff *)",
    "Bash(git grep *)",
    "Bash(git ls-files *)",
    "Bash(git show *)",
    "Bash(git status *)",
    "Bash(npm ls --depth=0 *)",
    "Bash(python -m pip show *)",
]


@dataclass
class GenerationResult:
    cases: list[FuzzCase]
    usage: LLMUsage | None = None


def generate_cases_with_usage(
    targets: Iterable[FuzzTarget],
    *,
    agent: str,
    repo_root: str | Path,
    model: str | None = None,
    provider: str | None = None,
    max_cases: int | None = None,
    max_turns: int | None = None,
    max_budget_usd: float | None = None,
    timeout_seconds: int = 600,
    capture_usage: bool = False,
) -> GenerationResult:
    if provider and agent != "codex":
        raise ValueError(
            "--provider currently applies only to --agent codex. For Claude Code, "
            "configure Anthropic, Bedrock, Vertex, Foundry, or an API gateway through "
            "Claude Code environment variables."
        )

    target_list = list(targets)
    if max_cases is not None:
        target_list = [replace(target, max_cases=max_cases) for target in target_list]
    if max_budget_usd is not None:
        if max_budget_usd <= 0:
            raise ValueError("--max-budget-usd must be greater than 0")
        target_list = [replace(target, budget_usd=max_budget_usd) for target in target_list]

    if agent not in {"codex", "claude"}:
        raise ValueError(f"Unsupported agent: {agent}")

    all_cases: list[FuzzCase] = []
    total_usage: LLMUsage | None = None
    root = Path(repo_root)
    for target in target_list:
        if agent == "codex":
            result = _generate_with_codex(
                [target],
                root,
                model=model,
                provider=provider,
                timeout_seconds=timeout_seconds,
                capture_usage=capture_usage,
            )
        else:
            result = _generate_with_claude(
                [target],
                root,
                model=model,
                max_turns=max_turns,
                max_budget_usd=target.budget_usd,
                timeout_seconds=timeout_seconds,
                capture_usage=capture_usage,
            )
        all_cases.extend(result.cases)
        total_usage = _merge_usage(total_usage, result.usage)

    return GenerationResult(all_cases, total_usage)


def _build_agent_prompt(targets: list[FuzzTarget], repo_root: Path) -> str:
    template = files("llm_fuzz_ci.prompts").joinpath("generate_cases.md").read_text()
    return (
        template.replace("{{REPO_ROOT}}", str(repo_root))
        .replace("{{TARGETS_JSON}}", json.dumps([target.to_dict() for target in targets], indent=2))
        .replace("{{EXAMPLE_INPUT_JSON}}", json.dumps(json.dumps({"x": 1, "y": 0})))
    )


def _merge_usage(total: LLMUsage | None, item: LLMUsage | None) -> LLMUsage | None:
    if item is None:
        return total
    if total is None:
        return item
    total.add(item)
    return total


def _generate_with_codex(
    targets: list[FuzzTarget],
    repo_root: Path,
    *,
    model: str | None,
    provider: str | None,
    timeout_seconds: int,
    capture_usage: bool,
) -> GenerationResult:
    help_text = _ensure_codex_exec_available()
    prompt = _build_agent_prompt(targets, repo_root)
    with tempfile.TemporaryDirectory(prefix="llm-fuzz-codex-") as tmpdir:
        tmp = Path(tmpdir)
        schema_path = tmp / "agent-output.schema.json"
        output_path = tmp / "agent-output.json"
        schema_path.write_text(json.dumps(AGENT_OUTPUT_SCHEMA), encoding="utf-8")

        cmd = _build_codex_exec_command(
            help_text=help_text,
            schema_path=schema_path,
            output_path=output_path,
            model=model,
            provider=provider,
            capture_usage=capture_usage,
        )
        cmd.append(prompt)
        env = _codex_env(provider)

        completed = subprocess.run(
            cmd,
            cwd=repo_root,
            env=env,
            text=True,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(_format_process_failure("Codex", cmd, completed))

        output_text = (
            output_path.read_text(encoding="utf-8")
            if output_path.exists()
            else completed.stdout
        )
        return GenerationResult(
            _parse_agent_cases(output_text),
            extract_usage_from_json_events(
                completed.stdout,
                provider=_usage_provider_for_codex(provider),
                model=model,
            )
            if capture_usage
            else None,
        )


def _generate_with_claude(
    targets: list[FuzzTarget],
    repo_root: Path,
    *,
    model: str | None,
    max_turns: int | None,
    max_budget_usd: float | None,
    timeout_seconds: int,
    capture_usage: bool,
) -> GenerationResult:
    prompt = _build_agent_prompt(targets, repo_root)
    cmd = _build_claude_command(
        prompt=prompt,
        model=model,
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
    )
    env = os.environ.copy()
    completed = subprocess.run(
        cmd,
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(_format_process_failure("Claude", cmd, completed))
    return GenerationResult(
        _parse_agent_cases(completed.stdout),
        extract_usage_from_json_events(
            completed.stdout,
            provider="anthropic",
            model=model,
        )
        if capture_usage
        else None,
    )


def _build_claude_command(
    *,
    prompt: str,
    model: str | None,
    max_turns: int | None,
    max_budget_usd: float | None,
) -> list[str]:
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(AGENT_OUTPUT_SCHEMA),
        "--permission-mode",
        "dontAsk",
        "--tools",
        CLAUDE_INSPECT_TOOLS,
        "--allowed-tools",
        *CLAUDE_ALLOWED_INSPECT_TOOLS,
    ]
    if model:
        cmd.extend(["--model", model])
    if max_turns is not None:
        cmd.extend(["--max-turns", str(max_turns)])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])
    return cmd


def _build_codex_exec_command(
    *,
    help_text: str,
    schema_path: Path,
    output_path: Path,
    model: str | None,
    provider: str | None,
    capture_usage: bool,
) -> list[str]:
    cmd = ["codex", "exec"]
    has_config = _codex_exec_help_has_flag(help_text, "--config")

    if _codex_exec_help_has_flag(help_text, "--sandbox"):
        cmd.extend(["--sandbox", "read-only"])
    elif has_config:
        cmd.extend(["--config", 'sandbox_mode="read-only"'])

    if _codex_exec_help_has_flag(help_text, "--ask-for-approval"):
        cmd.extend(["--ask-for-approval", "never"])
    elif has_config:
        cmd.extend(["--config", 'approval_policy="never"'])

    if provider:
        if not has_config:
            raise RuntimeError(
                "Codex provider selection requires a Codex CLI that supports "
                "`codex exec --config`. Update Codex CLI and retry."
            )
        _append_codex_provider_config(cmd, provider)

    cmd.extend(
        [
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
    )
    if model:
        cmd.extend(["--model", model])
    if capture_usage and _codex_exec_help_has_flag(help_text, "--json"):
        cmd.append("--json")
    return cmd


def _append_codex_provider_config(cmd: list[str], provider: str) -> None:
    provider_id = _codex_provider_id(provider)
    cmd.extend(["--config", _codex_config_arg("model_provider", provider_id)])
    for key, value in _codex_provider_shortcut_config(provider_id):
        cmd.extend(["--config", _codex_config_arg(key, value)])


def _codex_provider_id(provider: str) -> str:
    lowered = provider.lower()
    if lowered in {"openai", "openrouter"}:
        return lowered
    return provider


def _codex_provider_shortcut_config(provider: str) -> list[tuple[str, str]]:
    if provider != "openrouter":
        return []
    return [
        ("model_providers.openrouter.name", "OpenRouter"),
        ("model_providers.openrouter.base_url", "https://openrouter.ai/api/v1"),
        ("model_providers.openrouter.env_key", "OPENROUTER_API_KEY"),
        ("model_providers.openrouter.wire_api", "responses"),
    ]


def _codex_config_arg(key: str, value: str) -> str:
    return f"{key}={json.dumps(value)}"


def _usage_provider_for_codex(provider: str | None) -> str:
    if not provider:
        return "openai"
    return _codex_provider_id(provider)


def _codex_exec_help_has_flag(help_text: str, flag: str) -> bool:
    return flag in help_text


def _codex_env(provider: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if (
        provider is None or provider.lower() == "openai"
    ) and not env.get("CODEX_API_KEY") and env.get("OPENAI_API_KEY"):
        env["CODEX_API_KEY"] = env["OPENAI_API_KEY"]
    if (
        provider
        and provider.lower() == "openrouter"
        and not env.get("OPENROUTER_API_KEY")
    ):
        raise RuntimeError(
            "--provider openrouter requires OPENROUTER_API_KEY in the environment "
            "or the action's openrouter-api-key input."
        )
    return env


def _ensure_codex_exec_available() -> str:
    codex_path = shutil.which("codex")
    if codex_path is None:
        raise RuntimeError(
            "Codex CLI was not found on PATH.\n\n"
            "Install the current Codex CLI, then retry generation:\n"
            "  curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh\n\n"
            "If you are in GitHub Actions, leave the action's install-agent input set to true."
        )

    try:
        completed = subprocess.run(
            ["codex", "exec", "--help"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Timed out while checking whether Codex CLI at {codex_path} supports `codex exec`."
        ) from exc

    help_text = f"{completed.stdout}\n{completed.stderr}"
    supports_exec = (
        completed.returncode == 0
        and "--output-schema" in help_text
        and "--output-last-message" in help_text
    )
    if supports_exec:
        return help_text

    raise RuntimeError(
        "The installed Codex CLI does not support the non-interactive command required by LLM Fuzz CI.\n\n"
        f"Detected binary: {codex_path}\n"
        f"`codex exec --help` exit code: {completed.returncode}\n\n"
        "This commonly happens when an older npm-era `@openai/codex` binary appears first on PATH.\n"
        "Install or update the current Codex CLI, then open a new shell or make sure the new binary is first on PATH:\n"
        "  curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh\n\n"
        "Relevant help output:\n"
        f"{_clip(help_text.strip() or '(empty)', 4000)}"
    )


def _format_process_failure(
    tool_name: str,
    cmd: list[str],
    completed: subprocess.CompletedProcess[str],
) -> str:
    output = f"{completed.stdout}\n{completed.stderr}"
    diagnosis = _diagnose_process_failure(output)
    diagnosis_block = f"\nlikely cause: {diagnosis}\n" if diagnosis else ""
    return (
        f"{tool_name} generation failed\n"
        f"exit code: {completed.returncode}\n"
        f"command: {_format_command(cmd)}\n\n"
        f"{diagnosis_block}"
        f"stdout excerpt:\n{_failure_excerpt(completed.stdout)}\n\n"
        f"stderr excerpt:\n{_failure_excerpt(completed.stderr)}"
    )


def _format_command(cmd: list[str]) -> str:
    redacted: list[str] = []
    for part in cmd:
        if "\n" in part:
            redacted.append("<prompt>")
        else:
            redacted.append(part)
    return " ".join(redacted)


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... truncated ..."


def _diagnose_process_failure(output: str) -> str | None:
    lowered = output.lower()
    if "no credits remaining" in lowered:
        return (
            "the OpenAI API key reached the API, but its project or organization "
            "has no remaining credits; add billing credits or use a funded key"
        )
    if "invalid_json_schema" in lowered or "invalid schema for response_format" in lowered:
        return "the agent output JSON Schema is not accepted by the model provider"
    if "unexpected argument" in lowered:
        return "the installed agent CLI does not support one of the flags passed by LLM Fuzz CI"
    if "missing openai api key" in lowered or "api key" in lowered and "missing" in lowered:
        return "the selected agent did not receive an API key"
    return None


def _failure_excerpt(text: str, *, max_chars: int = 4000) -> str:
    redacted = _redact_secrets(text).strip()
    if not redacted:
        return "(empty)"

    important_lines = [
        line
        for line in redacted.splitlines()
        if _looks_like_failure_line(line)
    ]
    if important_lines:
        return _clip("\n".join(_dedupe_preserving_order(important_lines)), max_chars)
    return _clip(redacted, max_chars)


def _redact_secrets(text: str) -> str:
    return re.sub(r"sk-[A-Za-z0-9_-]+", "sk-redacted", text)


def _looks_like_failure_line(line: str) -> bool:
    lowered = line.lower()
    return (
        lowered.startswith("error")
        or " error=" in lowered
        or "error:" in lowered
        or "failed" in lowered
        or "invalid_" in lowered
        or "invalid schema" in lowered
        or "unauthorized" in lowered
        or "forbidden" in lowered
        or "no credits remaining" in lowered
        or "billing" in lowered
        or "unexpected argument" in lowered
        or "permission denied" in lowered
        or "operation not permitted" in lowered
    )


def _dedupe_preserving_order(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)
    return deduped


def _parse_agent_cases(output_text: str) -> list[FuzzCase]:
    raw = json.loads(_strip_markdown(output_text))
    if "result" in raw and isinstance(raw["result"], str):
        raw = json.loads(_strip_markdown(raw["result"]))
    if "cases" not in raw:
        raise ValueError("Agent output must contain a top-level 'cases' list")

    cases: list[FuzzCase] = []
    for item in raw["cases"]:
        cases.append(FuzzCase.from_dict(dict(item)))
    return cases


def _strip_markdown(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped
