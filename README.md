# LLM Fuzz CI

[![Tests](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml/badge.svg)](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml)

A GitHub Action that has a coding agent write adversarial inputs for your code,
then runs them against your own pytest assertions.

The agent only writes inputs. Your assertions decide pass or fail.

## Quick start

**1. Mark the tests you want fuzzed.** The `llm_fuzz_case` fixture holds one
generated input.

```python
import pytest

@pytest.mark.llm_fuzz
def test_rejects_untrusted_redirects(llm_fuzz_case):
    assert is_safe_redirect(llm_fuzz_case.input["url"]) is False
```

**2. Add `.github/workflows/llm-fuzz-ci.yml`.**

```yaml
name: LLM Fuzz CI

on:
  workflow_dispatch:

jobs:
  llm-fuzz-ci:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write

    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - uses: NDV-tiime/llm-fuzz-ci@v1
        with:
          test-paths: tests
          setup-command: python -m pip install -e .
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          create-issue: true
```

**3. Add `OPENAI_API_KEY`** under Settings → Secrets and variables → Actions,
then run the workflow from the Actions tab.

`setup-command` is how pytest imports your code. If your project has no
`pyproject.toml`, install your dependencies and add `pythonpath: .` (or
`pythonpath: src`) instead.

An annotated copy of this workflow is in
[`templates/llm-fuzz-ci.yml`](templates/llm-fuzz-ci.yml).

## Inputs

| Input | Default | Description |
| --- | --- | --- |
| `test-paths` | `tests` | pytest paths holding marked tests |
| `setup-command` | | shell command that installs your project |
| `pythonpath` | | import path, for code that is not installed |
| `agent` | `codex` | `codex` or `claude` |
| `model` | | model for the agent; empty uses its default |
| `provider` | | Codex provider, for example `openrouter` |
| `openai-api-key` | | key for `codex` |
| `openrouter-api-key` | | key for `provider: openrouter` |
| `anthropic-api-key` | | key for `claude` |
| `create-issue` | `false` | open an issue when an input fails |
| `hard-fail` | `true` | fail the workflow when an input fails |

Output: `failed-inputs`, the number of inputs that failed.

## Results

The run summary lists every marked test with its outcome, shows failing inputs
in full, and folds the rest away. The `llm-fuzz-ci-report` artifact has the same
run unfolded, plus `test-report.json` and `llm-usage.json`.

A failure means one of three things:

- **a real bug** — fix the code, and commit the input from the artifact into
  `.llm-fuzz/cases/` to keep the case;
- **an assertion that was too strict** — fix the test;
- **`invalid input`** — the agent guessed a key your function does not take.
  This never fails the build. Read the keys you want by name rather than
  passing `**llm_fuzz_case.input`.

## Cost

One agent run per marked test, per workflow run. Add `show-usage: true` to print
the token total.

`@pytest.mark.llm_fuzz(budget_usd=0.25)` is a hard per-test spend limit on
`claude`. The Codex CLI has no budget flag, so on `codex` it is advisory only.

## Agents

`codex` is the default. OpenAI's safety classifier sometimes refuses this
workload with `flagged for possible cybersecurity risk`; `agent: claude` is the
quickest way past it, [Trusted Access for Cyber](https://chatgpt.com/cyber) the
durable one.

The agent runs unrestricted so it can read your code. Linux and macOS runners
only.

## Keeping the agent away from your secrets

The workflow above runs generation and your tests in one job. If your marked
tests need application secrets, use the reusable workflow instead — it splits
them into two jobs and gives the generation job only the LLM key.

```yaml
jobs:
  llm-fuzz-ci:
    uses: NDV-tiime/llm-fuzz-ci/.github/workflows/llm-fuzz-ci.yml@v1
    permissions:
      contents: read
      issues: write
    with:
      test-paths: tests
      setup-command: python -m pip install -e .
      create-issue: true
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

It also accepts `working-directory`, `python-version`, `timeout-seconds`,
`show-usage` and `max-budget-usd`.

For service containers, a specific runner, or anything else the reusable
workflow does not expose, compose the three actions in your own jobs:
`actions/generate`, then `llm-fuzz-ci test-fuzz-cases`, then `actions/report`.
See [`.github/workflows/llm-fuzz-ci.yml`](.github/workflows/llm-fuzz-ci.yml) for
a working two-job version to copy.

## Pull requests

The quick start uses `workflow_dispatch`. The reusable workflow skips generation
for pull requests from forks; never use `pull_request_target` for a workflow
that checks out and runs pull request code.

## CLI

The action is a thin wrapper around a CLI you can run locally.

```bash
pip install "git+https://github.com/NDV-tiime/llm-fuzz-ci.git@v1"
export CODEX_API_KEY=...

llm-fuzz-ci collect tests
llm-fuzz-ci generate --dry-run     # print the prompt, spend nothing
llm-fuzz-ci generate
llm-fuzz-ci test-fuzz-cases --require-cases -- tests -q
llm-fuzz-ci summary
```

## Optional

`skills/` holds an agent skill for your editor that helps write the marked
tests. Nothing here needs it.

## License

MIT
