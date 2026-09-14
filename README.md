# LLM Fuzz CI

Generate adversarial inputs with Codex or Claude Code, then test them with your
own pytest assertions in GitHub Actions.

The coding agent only creates inputs. Your tests decide what is safe.

## Quick Start

Add `.github/workflows/llm-fuzz-ci.yml`:

```yaml
name: LLM Fuzz CI

on:
  workflow_dispatch:

jobs:
  llm-fuzz-ci:
    uses: llm-fuzz/llm-fuzz-ci/.github/workflows/llm-fuzz-ci.yml@v1
    permissions:
      contents: read
      issues: write
    with:
      test-paths: tests
      setup-command: |
        python -m pip install -r requirements.txt
        python -m pip install -e .
      pythonpath: src
      agent: codex
      model: gpt-5.6-terra
      create-issue: true
      hard-fail: true
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Then add `OPENAI_API_KEY` to your repository secrets.

## Mark A Test

```python
import pytest

from app import divide


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_divide_handles_adversarial_inputs(llm_fuzz_case):
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0")

    assert result is None or isinstance(result, (int, float))
```

`llm_fuzz_case.input` is one generated input object. `budget_usd` is required
and applies to that marked test.

## Read The Results

There are two surfaces, and they are deliberately different lengths.

**The GitHub Actions run summary** is a digest you can read without scrolling:

- a heading that states the verdict, for example `2 of 23 tested inputs failed`;
- one row per marked test, with input counts and pass/fail/not-tested totals;
- every failing input in full, expanded, with its payload and failure excerpt;
- then one collapsed section per marked test, holding every input it was given
  with its outcome, payload, and one line on what it probes;
- the agent, model, and token total.

Collapsed, each marked test costs one line, so the digest grows with how many
tests you marked rather than with how many inputs the agent produced. Long
payloads are truncated with a `(+N chars)` marker; a repository with 40 markers
and 320 inputs still opens to about 130 lines.

**The `llm-fuzz-ci-report` artifact** is the exhaustive version. Download it and
open `llm-fuzz-ci-report.md`, a single Markdown document:

- a summary table, and one sentence saying what the run means;
- failing inputs first, each with its input, rationale, and failure excerpt;
- then every generated input, grouped by target and marked `passed`, `failed`,
  or `not tested`;
- token usage when the agent reported it.

Inputs that were generated but never run show up as `not tested`. That usually
means the agent returned a `target_id` that matches no collected test, so those
inputs silently assert nothing.

The same folder keeps `test-report.json` and `llm-usage.json` for tooling.

If a generated input fails one of your marked tests:

- the workflow fails when `hard-fail: true`;
- a GitHub issue is created when `create-issue: true`;
- the issue contains the readable test report.

Issue creation requires GitHub Issues to be enabled and `issues: write`
permission in the workflow.

## Agents And Models

Use Codex:

```yaml
with:
  agent: codex
  model: gpt-5.6-terra
secrets:
  OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Use Claude Code:

```yaml
with:
  agent: claude
  model: sonnet
secrets:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

If the Anthropic console says your key is not tied to a workspace, the API
rejects every request with `400 ... must include the anthropic-workspace-id
header`. Either create the key inside a workspace, or name the workspace:

```yaml
with:
  agent: claude
  model: sonnet
  anthropic-workspace-id: ${{ vars.ANTHROPIC_WORKSPACE_ID }}
```

A workspace id is an identifier, not a credential, so a repository variable
suits it better than a secret.

Use OpenRouter through Codex:

```yaml
with:
  agent: codex
  provider: openrouter
  model: openai/gpt-5-mini
secrets:
  OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

## Workflow Inputs

| Input | Purpose |
| --- | --- |
| `test-paths` | pytest paths containing marked tests |
| `setup-command` | installs your project test dependencies |
| `pythonpath` | optional import path, useful for `src/` layouts |
| `agent` | `codex` or `claude` |
| `model` | model passed to the selected agent |
| `provider` | optional Codex provider, for example `openrouter` |
| `anthropic-workspace-id` | workspace for an Anthropic key not scoped to one |
| `max-budget-usd` | optional override for every marker budget |
| `max-cases` | optional maximum inputs per marked test |
| `show-usage` | prints token usage when available |
| `create-issue` | opens a GitHub issue on generated-input failure |
| `hard-fail` | fails the workflow on generated-input failure |

## Local Debugging

```bash
python -m pip install "git+https://github.com/llm-fuzz/llm-fuzz-ci.git@v1"
export CODEX_API_KEY="sk-replace-me"

llm-fuzz-ci collect tests --output .llm-fuzz/targets.json
llm-fuzz-ci generate --agent codex --model gpt-5.6-terra --show-usage
llm-fuzz-ci cases
llm-fuzz-ci test-fuzz-cases --require-cases -- tests -q
llm-fuzz-ci report --all --show-failure-details
llm-fuzz-ci summary --format overview --output .llm-fuzz/reports/overview.md
llm-fuzz-ci summary --output .llm-fuzz/reports/llm-fuzz-ci-report.md
```

`report` prints the pass/fail outcome for the terminal. `summary --format
overview` writes the digest CI puts in the run summary; `summary` on its own
writes the full document CI uploads as an artifact.

## Status

Implemented:

- GitHub reusable workflow;
- isolated generate and test jobs;
- Python/pytest support;
- Codex and Claude Code generation;
- readable GitHub Actions summaries;
- GitHub issue alerting;
- token usage reporting.

Not implemented yet:

- Node/Vitest support;
- automatic test/assertion generation;
- SARIF/code scanning output.
