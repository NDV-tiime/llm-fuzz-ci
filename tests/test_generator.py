import subprocess

import pytest

from llm_fuzz_ci import generator
from llm_fuzz_ci.generator import generate_cases_with_usage
from llm_fuzz_ci.schema import FuzzTarget
from llm_fuzz_ci.usage import LLMUsage


def test_parse_agent_cases_accepts_structured_output():
    cases = generator._parse_agent_cases(
        """
        {
          "cases": [
            {
              "input_json": "{\\"x\\": 1, \\"y\\": 0}",
              "rationale": "Division by zero"
            }
          ]
        }
        """,
        "tests/test_app.py::test_divide",
    )

    assert len(cases) == 1
    assert cases[0].target_id == "tests/test_app.py::test_divide"
    assert cases[0].input == {"x": 1, "y": 0}
    assert cases[0].rationale == "Division by zero"


def test_agent_prompt_is_rendered_from_template(tmp_path):
    prompt = generator._build_agent_prompt(
        [
            FuzzTarget(
                id="divide",
                target="pytest::tests/test_app.py::test_divide",
                budget_usd=0.25,
            )
        ],
        tmp_path,
    )

    assert "{{" not in prompt
    assert str(tmp_path) in prompt
    assert '"id": "divide"' in prompt
    assert '"budget_usd": 0.25' in prompt
    assert "Every case must include input_json and rationale." in prompt


def test_global_max_cases_overrides_agent_targets(monkeypatch):
    captured = {}

    def fake_codex(targets, repo_root, *, model, provider, timeout_seconds, capture_usage):
        captured["max_cases"] = [target.max_cases for target in targets]
        captured["provider"] = provider
        return generator.GenerationResult([])

    monkeypatch.setattr(generator, "_generate_with_codex", fake_codex)

    generate_cases_with_usage(
        [FuzzTarget(id="divide", target="app:divide", budget_usd=0.25, max_cases=9)],
        agent="codex",
        repo_root=".",
        max_cases=2,
    )

    assert captured["max_cases"] == [2]
    assert captured["provider"] is None


def test_claude_generation_uses_required_target_budget_per_target(monkeypatch):
    captured = []

    def fake_claude(
        targets,
        repo_root,
        *,
        model,
        max_turns,
        max_budget_usd,
        timeout_seconds,
        capture_usage,
    ):
        target = targets[0]
        captured.append((target.id, target.budget_usd, max_budget_usd))
        return generator.GenerationResult(
            [],
            LLMUsage(provider="anthropic", input_tokens=10, output_tokens=5, total_tokens=15),
        )

    monkeypatch.setattr(generator, "_generate_with_claude", fake_claude)

    result = generate_cases_with_usage(
        [
            FuzzTarget(id="checkout", target="app:checkout", budget_usd=0.25),
            FuzzTarget(id="redirect", target="app:redirect", budget_usd=0.10),
        ],
        agent="claude",
        repo_root=".",
        capture_usage=True,
    )

    assert captured == [
        ("checkout", 0.25, 0.25),
        ("redirect", 0.10, 0.10),
    ]
    assert result.usage is not None
    assert result.usage.total_tokens == 30


def test_global_max_budget_overrides_marker_budget_per_target(monkeypatch):
    captured = []

    def fake_claude(
        targets,
        repo_root,
        *,
        model,
        max_turns,
        max_budget_usd,
        timeout_seconds,
        capture_usage,
    ):
        target = targets[0]
        captured.append((target.id, target.budget_usd, max_budget_usd))
        return generator.GenerationResult([])

    monkeypatch.setattr(generator, "_generate_with_claude", fake_claude)

    generate_cases_with_usage(
        [
            FuzzTarget(id="checkout", target="app:checkout", budget_usd=0.25),
            FuzzTarget(id="redirect", target="app:redirect", budget_usd=0.10),
        ],
        agent="claude",
        repo_root=".",
        max_budget_usd=0.50,
    )

    assert captured == [
        ("checkout", 0.50, 0.50),
        ("redirect", 0.50, 0.50),
    ]


def test_codex_preflight_rejects_old_cli(monkeypatch):
    monkeypatch.setattr(generator.shutil, "which", lambda name: "/fake/bin/codex")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=2,
            stdout="Usage\n  $ codex [options] <prompt>",
            stderr="",
        )

    monkeypatch.setattr(generator.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="does not support the non-interactive command"):
        generator._ensure_codex_exec_available()


def test_codex_command_uses_config_approval_when_flag_is_absent(tmp_path):
    help_text = """
    Usage: codex exec [OPTIONS] [PROMPT]
      -s, --sandbox <SANDBOX_MODE>
          --config <key=value>
          --output-schema <FILE>
      -o, --output-last-message <FILE>
          --json
    """

    cmd = generator._build_codex_exec_command(
        help_text=help_text,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        model="gpt-5.6-terra",
        provider=None,
        capture_usage=True,
    )

    assert "--ask-for-approval" not in cmd
    assert cmd[:4] == ["codex", "exec", "--sandbox", "read-only"]
    assert "--config" in cmd
    assert 'approval_policy="never"' in cmd
    assert "--output-schema" in cmd
    assert "--output-last-message" in cmd
    assert "--json" in cmd
    model_index = cmd.index("--model")
    assert cmd[model_index + 1] == "gpt-5.6-terra"


def test_codex_command_keeps_ask_for_approval_when_flag_exists(tmp_path):
    help_text = """
    Usage: codex exec [OPTIONS] [PROMPT]
      --sandbox <SANDBOX_MODE>
      --ask-for-approval <MODE>
      --config <key=value>
      --output-schema <FILE>
      --output-last-message <FILE>
    """

    cmd = generator._build_codex_exec_command(
        help_text=help_text,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        model=None,
        provider=None,
        capture_usage=False,
    )

    assert "--ask-for-approval" in cmd
    assert "never" in cmd
    assert 'approval_policy="never"' not in cmd
    assert "--json" not in cmd


def test_claude_command_allows_inspection_without_web_or_edit_tools():
    cmd = generator._build_claude_command(
        prompt="Generate cases",
        model="sonnet",
        max_turns=4,
        max_budget_usd=0.5,
    )

    assert "Read,Grep,Glob,Bash" in cmd
    assert "--allowed-tools" in cmd
    assert "Bash(git diff *)" in cmd
    assert "WebSearch" not in cmd
    assert "WebFetch" not in cmd
    assert "Edit" not in cmd
    assert "Write" not in cmd
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--max-turns") + 1] == "4"
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.5"


def test_codex_command_can_select_openrouter_provider(tmp_path):
    help_text = """
    Usage: codex exec [OPTIONS] [PROMPT]
      --sandbox <SANDBOX_MODE>
      --config <key=value>
      --output-schema <FILE>
      --output-last-message <FILE>
    """

    cmd = generator._build_codex_exec_command(
        help_text=help_text,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        model="openrouter/model-slug",
        provider="openrouter",
        capture_usage=False,
    )

    assert "--config" in cmd
    assert 'model_provider="openrouter"' in cmd
    assert 'model_providers.openrouter.base_url="https://openrouter.ai/api/v1"' in cmd
    assert 'model_providers.openrouter.env_key="OPENROUTER_API_KEY"' in cmd
    assert 'model_providers.openrouter.wire_api="responses"' in cmd


def test_codex_openrouter_shortcut_is_case_insensitive(tmp_path):
    help_text = """
    Usage: codex exec [OPTIONS] [PROMPT]
      --config <key=value>
      --output-schema <FILE>
      --output-last-message <FILE>
    """

    cmd = generator._build_codex_exec_command(
        help_text=help_text,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        model=None,
        provider="OpenRouter",
        capture_usage=False,
    )

    assert 'model_provider="openrouter"' in cmd


def test_non_codex_provider_is_rejected():
    with pytest.raises(ValueError, match="applies only to --agent codex"):
        generate_cases_with_usage(
            [FuzzTarget(id="divide", target="app:divide", budget_usd=0.25)],
            agent="claude",
            repo_root=".",
            provider="openrouter",
        )


def test_openrouter_provider_requires_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        generator._codex_env("openrouter")


def test_process_failure_summarizes_billing_error_and_redacts_key():
    completed = subprocess.CompletedProcess(
        args=["codex"],
        returncode=1,
        stdout="",
        stderr=(
            "user\n"
            "very long prompt body\n"
            "ERROR: stream disconnected before completion: You have no credits remaining. "
            "Add credits to continue using the API. key sk-proj-secret\n"
        ),
    )

    message = generator._format_process_failure("Codex", ["codex", "exec"], completed)

    assert "likely cause:" in message
    assert "no remaining credits" in message
    assert "sk-proj-secret" not in message
    assert "sk-redacted" in message
    assert "very long prompt body" not in message


def test_process_failure_explains_a_workspaceless_api_key():
    completed = subprocess.CompletedProcess(
        args=["claude"],
        returncode=1,
        stdout=(
            '{"is_error":true,"api_error_status":400,"result":"API Error: 400 This API key '
            "is not scoped to a workspace, so this request must include the "
            'anthropic-workspace-id header with the ID of the workspace to use."}'
        ),
        stderr="",
    )

    message = generator._format_process_failure("Claude", ["claude"], completed)

    assert "likely cause:" in message
    assert "anthropic-workspace-id input" in message


def test_process_failure_explains_a_provider_policy_refusal():
    completed = subprocess.CompletedProcess(
        args=["codex"],
        returncode=1,
        stdout=(
            '{"type":"turn.failed","error":{"message":"This content was flagged for '
            'possible cybersecurity risk."}}'
        ),
        stderr="",
    )

    message = generator._format_process_failure("Codex", ["codex"], completed)

    assert "refused the request under its cybersecurity" in message
    assert "--agent claude" in message
