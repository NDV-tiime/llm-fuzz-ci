# LLM Fuzz CI

[![Tests](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml/badge.svg)](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml)

Fuzz your Python or JavaScript code with a coding agent, in GitHub Actions.

Mark a test. The agent reads your code and writes adversarial inputs for it.

## Quick start

Mark the tests you want fuzzed. The agent fills the input with arguments for the call.

```python
import pytest

@pytest.mark.llm_fuzz(budget_usd=0.5)
def test_foo(llm_fuzz_case):
    result = foo(**llm_fuzz_case.input)
    assert "<script>" not in result
```

For vitest, `npm install --save-dev github:NDV-tiime/llm-fuzz-ci` and mark it the same way:

```js
import { expect } from "vitest";
import { fuzzTest } from "llm-fuzz-ci";

fuzzTest("foo escapes its input", { budgetUsd: 0.5 }, (input) => {
  expect(foo(input.value)).not.toContain("<script>");
});
```

Add `.github/workflows/llm-fuzz-ci.yml`:

```yaml
name: LLM Fuzz CI

on:
  workflow_dispatch:

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      # Set the project up however you normally do.
      - run: pip install -e .

      - uses: NDV-tiime/llm-fuzz-ci/actions/generate@v1
        with:
          test-paths: tests
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}

  test:
    needs: generate
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      # The same setup again.
      - run: pip install -e .

      - uses: NDV-tiime/llm-fuzz-ci@v1
        with:
          test-paths: tests
          create-issue: true
```

Run it from the Actions tab.

Set each job up the way you would for any other test run: dependencies in steps before the action, databases and queues in `services`, configuration in the job's `env`. If pytest can import your code there, so can the action.

An annotated copy of this workflow is in
[`templates/llm-fuzz-ci.yml`](templates/llm-fuzz-ci.yml).

## Marker options

| Argument | Description |
| --- | --- |
| `budget_usd` | Per-test spend limit. |
| `params` | Limit generation to these input keys. Without it the agent works out the whole signature from your harness. |

```python
@pytest.mark.llm_fuzz(budget_usd=0.5, params=["amount"])
def test_transfer(llm_fuzz_case):
    result = transfer(account_id="acct_1", amount=llm_fuzz_case.input["amount"])
    assert result.amount >= 0
```

## Configuration

`actions/generate` — the job that runs the agent:

| Input | Default | Description |
| --- | --- | --- |
| `test-paths` | `tests` | paths holding marked tests |
| `runner` | `auto` | `pytest`, `vitest`, or `auto` from the path |
| `agent` | `codex` | `codex` or `claude` |
| `model` | | model for the agent; empty uses its default |
| `provider` | | Codex provider, for example `openrouter` |
| `openai-api-key` | | key for `codex` |
| `openrouter-api-key` | | key for `provider: openrouter` |
| `anthropic-api-key` | | key for `claude` |

`NDV-tiime/llm-fuzz-ci` — the job that runs the inputs and reports:

| Input | Default | Description |
| --- | --- | --- |
| `test-paths` | `tests` | must match the generate job |
| `runner` | `auto` | must match the generate job |
| `create-issue` | `false` | open an issue when an input fails |
| `issue-assignees` | | comma-separated logins to assign it to |
| `issue-labels` | | comma-separated labels to put on it |
| `hard-fail` | `true` | fail the workflow when an input fails |

Outputs `failed-inputs`, the number of inputs that failed their test.

## Alerts

Every run writes a summary to the Actions run page: one row per marked test with its outcome, each failing input in full with the assertion that fired. The `llm-fuzz-ci-report` artifact holds the same run unfolded, plus `test-report.json` and `llm-usage.json`, and `agent-trace/`, a transcript per test of what the agent reasoned, ran, and saw.

All of the following are off unless you turn them on.

**An issue.** With `create-issue: true` every failing run opens one, titled with the number of failing inputs and linking back to the run. Needs `issues: write`.

**An email.** GitHub emails the assignee of an issue, use`issue-assignees: you` and `issue-labels`.

**A red build.** `hard-fail: true`, the default. The failure is the last thing the action does, so the summary, the artifact and the issue all land first. It fails the job, which skips the steps after it and any job that `needs:` it; jobs already running in parallel are not cancelled.

**Anything else.** The action outputs `failed-inputs`, so a step of your own can post to Slack, Teams, or a pager:

Set `hard-fail: false` when you do that, or the job dies before your step runs.

## Agents

| Agent | Key |
| --- | --- |
| `codex` (default) | `openai-api-key`, or `openrouter-api-key` with `provider: openrouter` |
| `claude` | `anthropic-api-key` |

OpenAI's safety classifier sometimes refuses this workload with `flagged for possible cybersecurity risk`. `agent: claude` is the quickest way past it; [Trusted Access for Cyber](https://chatgpt.com/cyber) is the durable one.

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
[`skills/SKILL.md`](skills/SKILL.md) is an agent skill for exactly that: it picks
out the functions worth fuzzing, writes the marked tests.

## License

MIT
