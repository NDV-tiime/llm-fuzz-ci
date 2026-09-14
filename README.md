# LLM Fuzz CI

Adversarial input generation for GitHub Actions.

LLM Fuzz CI uses Codex or Claude Code to inspect your marked tests and generate
inputs that are likely to break security-sensitive code. Those inputs are then
replayed by pytest using your own assertions.

The agent generates **inputs only**. It does not write tests, write assertions,
or decide whether the run passed.

## Quick Start

Add this workflow to `.github/workflows/llm-fuzz-ci.yml`:

```yaml
name: LLM Fuzz CI

on:
  pull_request:
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

That is the normal setup. You do not need to install the Python package in your
repository just to use the GitHub workflow; the workflow installs its own runner
tooling.

## Mark Tests To Fuzz

In your pytest suite, mark the tests that should receive generated inputs:

```python
import pytest

from app import divide


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_divide_handles_fuzz_cases(llm_fuzz_case):
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0")

    assert result is None or isinstance(result, (int, float))
```

The marker declares a target. The fixture provides one generated input at a
time through `llm_fuzz_case.input`.

`budget_usd` is required. It is the generation budget for that marked test.

If another pytest job also selects these tests, install LLM Fuzz CI from GitHub
in that job too, or keep fuzz harnesses in a path that only this workflow runs.

## What Happens In CI

The reusable workflow runs two isolated jobs:

1. **Generate**: Codex or Claude Code reads the repository and writes JSONL
   input cases. Each marked test is generated in its own agent run.
2. **Replay**: a fresh checkout runs pytest against those cases.

If replay fails, the workflow fails. If `create-issue: true` is enabled, the
workflow also opens a GitHub issue containing the failing input and pytest
failure excerpt.

Issue creation requires:

- GitHub Issues enabled on the repository.
- `issues: write` in workflow permissions.

## Generated Case Format

Cases are saved under `.llm-fuzz/cases/*.jsonl`.

```json
{"target_id":"tests/test_app.py::test_divide_handles_fuzz_cases","input":{"x":1,"y":0},"category":"zero-denominator","rationale":"Checks unguarded division by zero."}
```

Fields:

- `target_id`: marked pytest test id.
- `input`: data passed to the test.
- `category`: short label.
- `rationale`: why the input is interesting.

## Configuration

Common workflow inputs:

| Input | Purpose |
| --- | --- |
| `test-paths` | pytest paths to collect and replay |
| `setup-command` | installs your project dependencies before pytest runs |
| `pythonpath` | useful for `src/` layouts or unpackaged repos |
| `agent` | `codex` or `claude` |
| `model` | model name passed to the selected agent |
| `provider` | optional Codex provider, for example `openrouter` |
| `max-budget-usd` | optional override for every marker budget |
| `max-cases` | optional maximum cases per marked test |
| `show-usage` | prints token usage when available |
| `create-issue` | opens a GitHub issue on replay failure |
| `hard-fail` | fails the workflow on replay failure |

Claude Code example:

```yaml
with:
  agent: claude
  model: sonnet
secrets:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

OpenRouter through Codex:

```yaml
with:
  agent: codex
  provider: openrouter
  model: openai/gpt-5-mini
secrets:
  OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

## Budgets

Every `@pytest.mark.llm_fuzz` marker must include `budget_usd`.

LLM Fuzz CI runs generation once per marked test. With Claude Code, that value
is passed as `--max-budget-usd` for that single target. With Codex, the current
generic Codex CLI does not expose an equivalent hard budget flag, so the value
is included in the target metadata and prompt; use workflow timeouts and
provider-side limits as backstops.

`max-budget-usd` in the workflow or CLI overrides every marker budget for that
run.

## Blocking Merges And Deployments

`hard-fail: true` fails the workflow. To make that block releases:

- make `LLM Fuzz CI` a required status check on protected branches;
- make deployment jobs depend on it with `needs: llm-fuzz-ci`;
- deploy production only from protected branches.

```yaml
jobs:
  llm-fuzz-ci:
    uses: llm-fuzz/llm-fuzz-ci/.github/workflows/llm-fuzz-ci.yml@v1
    with:
      hard-fail: true
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

  deploy:
    needs: llm-fuzz-ci
    runs-on: ubuntu-latest
    steps:
      - run: ./deploy.sh
```

## Local Debugging

Local runs are useful when you want to inspect generated cases before pushing.

```bash
python -m pip install "git+https://github.com/llm-fuzz/llm-fuzz-ci.git@v1"
export CODEX_API_KEY="sk-replace-me"

llm-fuzz-ci collect tests --output .llm-fuzz/targets.json
llm-fuzz-ci generate --agent codex --model gpt-5.6-terra --show-usage
llm-fuzz-ci replay --require-cases -- tests -q
llm-fuzz-ci report --show-failure-details
```

For local development from this repository:

```bash
cd /Users/utilisateur/Documents/LLM/llm-fuzz/llm-fuzz-ci
python -m pip install -e .
```

## Demo

```bash
cd /Users/utilisateur/Documents/LLM/llm-fuzz/llm-fuzz-ci
python -m pip install -e .

cd demos/demo-codebase
python -m pip install -e .

export CODEX_API_KEY="sk-replace-me"

llm-fuzz-ci collect tests --output .llm-fuzz/targets.json
llm-fuzz-ci generate --agent codex --model gpt-5.6-terra --show-usage
llm-fuzz-ci replay --require-cases -- tests -q
llm-fuzz-ci report --show-failure-details
```

## Status

Implemented:

- Python/pytest replay.
- Codex and Claude Code generation.
- GitHub reusable workflow.
- GitHub issue alerting.
- token usage reporting.

Not implemented yet:

- Node/Vitest replay.
- automatic test/assertion generation.
- SARIF/code scanning output.
