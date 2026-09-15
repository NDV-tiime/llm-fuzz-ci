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
def test_foo(llm_fuzz_case):
    result = foo(llm_fuzz_case.input["value"])
    assert "<script>" not in result
```

The marker takes two optional arguments.

| Argument | Description |
| --- | --- |
| `params` | Limit generation to these input keys. Without it the agent infers them from the harness. |
| `budget_usd` | Per-test spend limit. Enforced on `claude` only — the Codex CLI has no budget flag. |

```python
@pytest.mark.llm_fuzz(params=["amount"], budget_usd=0.25)
def test_transfer(llm_fuzz_case):
    result = transfer(account_id="acct_1", amount=llm_fuzz_case.input["amount"])
    assert result.amount >= 0
```

With `params`, the agent is told the exact keys to produce and anything else it
returns is dropped before the test sees it. Use it whenever only part of the
input is attacker-controlled.

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

      # Set the project up however you normally do.
      - run: pip install -e .

      - uses: NDV-tiime/llm-fuzz-ci@v1
        with:
          test-paths: tests
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          create-issue: true
```

Run it from the Actions tab.

Everything happens in one job, so set the project up the way you would for any
other test run: dependencies in steps before the action, databases and queues in
`services`, configuration and credentials in the job's `env`. If pytest can
import your code in that job, so can the action. The agent runs there too, so it
sees whatever the job sees.

An annotated copy of this workflow is in
[`templates/llm-fuzz-ci.yml`](templates/llm-fuzz-ci.yml).

## Configuration

| Input | Default | Description |
| --- | --- | --- |
| `test-paths` | `tests` | pytest paths holding marked tests |
| `agent` | `codex` | `codex` or `claude` |
| `model` | | model for the agent; empty uses its default |
| `provider` | | Codex provider, for example `openrouter` |
| `openai-api-key` | | key for `codex` |
| `openrouter-api-key` | | key for `provider: openrouter` |
| `anthropic-api-key` | | key for `claude` |
| `create-issue` | `false` | open an issue when an input fails |
| `hard-fail` | `true` | fail the workflow when an input fails |

Outputs `failed-inputs`, the number of inputs that failed their test.

## Alerts

Every run writes a summary to the Actions run page: one row per marked test with
its outcome, each failing input in full with the assertion that fired, and the
rest folded away. The `llm-fuzz-ci-report` artifact holds the same run unfolded,
plus `test-report.json` and `llm-usage.json` if you want to process it.

When an input fails and `create-issue: true`, the action opens a GitHub issue
containing that summary. This needs `issues: write` in the job's `permissions`.

With `hard-fail: true`, the default, a failing input also fails the workflow.
Set it to `false` to get the summary and the issue without a red build.

## Compatibility

| | |
| --- | --- |
| Languages | Python 3.10+ |
| Test runners | pytest 8+ |
| Agents | Codex CLI, Claude Code |
| Models | any model the chosen agent accepts |
| Providers | OpenAI, Anthropic, OpenRouter (through Codex) |
| Runners | Linux, macOS |

## Cost

One agent run per marked test, per workflow run. Set `show-usage: true` to print
the token total in the job log.

## Agents

| Agent | Key |
| --- | --- |
| `codex` (default) | `openai-api-key`, or `openrouter-api-key` with `provider: openrouter` |
| `claude` | `anthropic-api-key` |

OpenAI's safety classifier sometimes refuses this workload with `flagged for
possible cybersecurity risk`. `agent: claude` is the quickest way past it;
[Trusted Access for Cyber](https://chatgpt.com/cyber) is the durable one.

The agent runs unrestricted so it can read your code.

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
