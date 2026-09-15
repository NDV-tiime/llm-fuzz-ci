# LLM Fuzz CI

[![Tests](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml/badge.svg)](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml)

Fuzz your Python code with a coding agent, in GitHub Actions.

Mark a test. The agent reads your code and writes adversarial inputs for it.
Your assertions decide whether any of them are a problem — the agent never
writes assertions and never decides pass or fail.

## Quick start

Mark the tests you want fuzzed. The `llm_fuzz_case` fixture holds one generated
input.

```python
import pytest

@pytest.mark.llm_fuzz
def test_rejects_untrusted_redirects(llm_fuzz_case):
    assert is_safe_redirect(llm_fuzz_case.input["url"]) is False
```

Add `.github/workflows/llm-fuzz-ci.yml`:

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

Run it from the Actions tab.

`setup-command` is how pytest imports your code. If your project has no
`pyproject.toml`, install your dependencies there and add `pythonpath: .` — or
`pythonpath: src` for a src layout.

An annotated copy of this workflow is in
[`templates/llm-fuzz-ci.yml`](templates/llm-fuzz-ci.yml).

## Configuration

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

Outputs `failed-inputs`, the number of inputs that failed their test.

## Results

The run summary lists every marked test with its outcome, shows failing inputs
in full, and folds the rest away. The `llm-fuzz-ci-report` artifact holds the
same run unfolded, alongside `test-report.json` and `llm-usage.json`.

A failure is one of three things:

| | |
| --- | --- |
| **A real bug** | Fix the code. Copy the input from the artifact into `.llm-fuzz/cases/` to keep the case forever. |
| **A strict assertion** | The input was legitimate. Fix the test. |
| **`invalid input`** | The agent guessed a key your function does not take. Never fails the build. Read the keys you want by name instead of passing `**llm_fuzz_case.input`. |

## Cost

One agent run per marked test, per workflow run. Set `show-usage: true` to print
the token total in the job log.

`@pytest.mark.llm_fuzz(budget_usd=0.25)` is a hard per-test spend limit on
`claude`. The Codex CLI has no budget flag, so on `codex` the number is advisory.

## Agents

| Agent | Key |
| --- | --- |
| `codex` (default) | `openai-api-key`, or `openrouter-api-key` with `provider: openrouter` |
| `claude` | `anthropic-api-key` |

OpenAI's safety classifier sometimes refuses this workload with `flagged for
possible cybersecurity risk`. `agent: claude` is the quickest way past it;
[Trusted Access for Cyber](https://chatgpt.com/cyber) is the durable one.

The agent runs unrestricted so it can read your code. Linux and macOS runners
only.

## Two jobs instead of one

The quick start runs generation and your tests in a single job. The reusable
workflow splits them, so the agent runs with only the LLM key and your tests run
with everything else.

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

It also takes `working-directory`, `python-version`, `timeout-seconds`,
`show-usage` and `max-budget-usd`.

For service containers, a specific runner, or anything else, build the jobs
yourself from the three actions — `actions/generate`, then
`llm-fuzz-ci test-fuzz-cases`, then `actions/report`. The reusable workflow in
[`.github/workflows/llm-fuzz-ci.yml`](.github/workflows/llm-fuzz-ci.yml) is a
working example to copy.

## Command line

The action wraps a CLI you can run locally.

```bash
pip install "git+https://github.com/NDV-tiime/llm-fuzz-ci.git@v1"
export CODEX_API_KEY=...

llm-fuzz-ci collect tests                                   # find marked tests
llm-fuzz-ci generate --dry-run                              # print the prompt, spend nothing
llm-fuzz-ci generate                                        # write .llm-fuzz/cases
llm-fuzz-ci test-fuzz-cases --require-cases -- tests -q     # run them
llm-fuzz-ci summary                                         # render the report
```

## Help writing the tests

Choosing what to fuzz and what to assert is the part that takes thought.
[`skills/`](skills) holds an agent skill for exactly that: point your editor's
coding agent at it and ask it to add coverage. It picks out the functions worth
fuzzing, writes the marked tests, and suggests invariants that catch real
problems rather than checking for `not None`.

`skills/SKILL.md` is the Claude Code format, `skills/openai.yaml` the OpenAI
one. The action never reads either — they are for you, before CI runs.

## License

MIT
