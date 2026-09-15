# LLM Fuzz CI

[![Tests](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml/badge.svg)](https://github.com/NDV-tiime/llm-fuzz-ci/actions/workflows/tests.yml)

A coding agent writes adversarial inputs for your code. Your own pytest
assertions decide whether any of them are a problem.

The agent never writes assertions, and never decides pass or fail.

## What you get

Every run leaves this in the Actions summary:

> ### LLM Fuzz CI
>
> | Test | Inputs | Outcome |
> | --- | --: | --- |
> | `test_divide_handles_adversarial_inputs` | 2 | 1 passed · 1 failed |
>
> **1 of 2 tested inputs failed.**
>
> **Failures — `test_divide_handles_adversarial_inputs`**
>
> Why this input: A zero divisor is the obvious unguarded path.
>
> ```json
> {"x": 1, "y": 0}
> ```
>
> ```text
> E  ZeroDivisionError: division by zero
> E  Failed: divide should handle y=0
> ```

Failing inputs are shown in full. Everything else folds away behind one section
per test, and the complete run is attached as an artifact.

## Setup

**1. Mark a test.** Take the input from `llm_fuzz_case.input`, call your code,
assert what must stay true.

```python
import pytest

from app import divide


@pytest.mark.llm_fuzz
def test_divide_handles_adversarial_inputs(llm_fuzz_case):
    """Division must not leak a raw ZeroDivisionError."""
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0")

    assert result is None or isinstance(result, (int, float))
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

`setup-command` is how pytest gets to import your code. Pick the one that
matches your project:

| Your project | Use |
| --- | --- |
| has a `pyproject.toml` or `setup.py` | `setup-command: python -m pip install -e .` |
| has only a `requirements.txt` | `setup-command: python -m pip install -r requirements.txt` plus `pythonpath: .` |
| keeps code under `src/` | the install above plus `pythonpath: src` |

If `collect` cannot import your code it says so and the job stops, so you will
know on the first run rather than after paying for one.

**3. Add `OPENAI_API_KEY`** under Settings → Secrets and variables → Actions,
then run the workflow from the Actions tab.

[`templates/llm-fuzz-ci.yml`](templates/llm-fuzz-ci.yml) is the same file with
every option annotated.

## Keeping the agent away from your secrets

The workflow above runs generation and your test suite in one job, so the agent
shares an environment with whatever that job can see. That is fine when your
marked tests are pure functions. When they need application secrets, use the
reusable workflow instead: it splits the work into two jobs and gives the
generation job nothing but the LLM key.

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

Service containers, a specific runner, or a monorepo subdirectory need your own
jobs — see [Bigger projects](#bigger-projects).

## Choosing what gets fuzzed

The agent infers the input keys from your harness: which keys you read off
`llm_fuzz_case.input`, and what the code under test does with them. The harness
is the parameter spec.

```python
# the agent controls the whole signature
divide(**llm_fuzz_case.input)

# the agent controls amount; account_id stays pinned
transfer(account_id="acct_1", amount=llm_fuzz_case.input["amount"])
```

Prefer the second form when only part of the input is attacker-controlled. It
also avoids a `TypeError` if the agent invents a key the function does not take.

## Inputs

Only `test-paths` and `setup-command` matter for most repositories.

| Input | Default | Purpose |
| --- | --- | --- |
| `test-paths` | `tests` | pytest paths holding marked tests |
| `setup-command` | none | shell command that installs your test dependencies |
| `pythonpath` | none | extra import path, for code not pip-installed |
| `agent` | `codex` | `codex` or `claude` |
| `model` | agent default | model for the selected agent |
| `provider` | none | Codex provider, for example `openrouter` |
| `create-issue` | `false` | open an issue when a generated input fails |
| `hard-fail` | `true` | fail the workflow when a generated input fails |

The reusable workflow adds `working-directory`, `python-version`,
`timeout-seconds`, `show-usage` and `max-budget-usd`.

`setup-command` runs before target collection and again before the tests. The
action cannot guess how to install your project, so this is where you say it.
It can also export environment variables for the test run:

```yaml
setup-command: |
  echo "ENV=ci" >> $GITHUB_ENV
  python -m pip install -e .
```

## Cost

One agent run per marked test, per workflow run — usually a few cents each.
`show-usage` prints the token total. Worth a look before you mark fifty tests.

`@pytest.mark.llm_fuzz(budget_usd=0.25)` sets a hard per-test spend limit **on
Claude Code only**. The Codex CLI has no budget flag, so there the number only
reaches the model as text. Control Codex spend with `model` and with how many
tests you mark.

## Agents

| Agent | Secret |
| --- | --- |
| `codex` | `OPENAI_API_KEY`, or `OPENROUTER_API_KEY` with `provider: openrouter` |
| `claude` | `ANTHROPIC_API_KEY` |

OpenAI's safety classifier sometimes refuses this workload with `flagged for
possible cybersecurity risk`. Switching to `agent: claude` is the quickest way
through; [Trusted Access for Cyber](https://chatgpt.com/cyber) is the durable one.

The agent runs unrestricted so it can read whatever it needs. Linux and macOS
runners only.

## Reading the results

The run summary is a digest, written once the tests have run. The
`llm-fuzz-ci-report` artifact holds the same run without folding or size limits,
plus `test-report.json` and `llm-usage.json` for tooling.

Inputs marked `not tested` were generated but matched no collected test, so they
asserted nothing. Inputs the agent returned malformed are reported as discarded
rather than failing the run.

## Your build went red. Now what?

The report names the test, the exact input, and the assertion that fired. Three
things it can mean:

**A real bug.** The input is one your code could genuinely receive. Fix the
code. Commit the input so the case is permanent — the corpus is a directory of
JSONL files and belongs in git like any other fixture.

**A bad assertion.** The input is legitimate and the test was too strict. Fix
the assertion.

**An input your function cannot take.** Shown as `invalid input`, not a
failure, and it never opens an issue. It means the agent guessed a key wrong.
Read the keys you want by name instead of splatting:

```python
transfer(account_id="acct_1", amount=llm_fuzz_case.input["amount"])
```

Nothing is remembered between runs unless you commit it. Each run regenerates
the corpus from scratch, so an unfixed finding may or may not come back.

## Running it locally

```bash
python -m pip install "git+https://github.com/NDV-tiime/llm-fuzz-ci.git@v1"
export CODEX_API_KEY="sk-replace-me"

llm-fuzz-ci collect tests
llm-fuzz-ci generate
llm-fuzz-ci test-fuzz-cases --require-cases -- tests -q
llm-fuzz-ci summary
```

`generate --dry-run` prints exactly what would be sent to the agent and exits
without spending anything — useful for checking a new harness reads the way you
expect. `summary --format overview` writes the folded digest CI puts in the run
summary.

## Bigger projects

Use the three actions in your own jobs when you need service containers, a
specific runner, or secrets kept out of the generation job.

```yaml
jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - uses: NDV-tiime/llm-fuzz-ci/actions/generate@v1
        with:
          test-paths: tests
          setup-command: python -m pip install -e .
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}

      - uses: actions/upload-artifact@v7
        with:
          name: llm-fuzz-cases
          path: .llm-fuzz

  test:
    needs: generate
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
        ports: ["5432:5432"]

    steps:
      - uses: actions/checkout@v7
      - uses: actions/download-artifact@v8
        with:
          name: llm-fuzz-cases
          path: .llm-fuzz
      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"
      - uses: NDV-tiime/llm-fuzz-ci/actions/setup@v1

      - run: python -m pip install -e ".[test]"

      - run: llm-fuzz-ci test-fuzz-cases --require-cases -- tests -q
        continue-on-error: true
        env:
          DATABASE_URL: postgres://postgres:postgres@localhost:5432/postgres

      - uses: NDV-tiime/llm-fuzz-ci/actions/report@v1
        if: always()
        with:
          create-issue: true
```

`actions/report` renders the summary and artifact, opens the issue and fails the
job, so the only thing you write is your own setup.

## Running on pull requests

The quick start uses `workflow_dispatch` on purpose. A fork pull request must
never reach the generation job with secrets — the reusable workflow already
skips generation there. Never use `pull_request_target` for a workflow that
checks out and runs pull request code.

On a public repository, consider generating only on `schedule` or
`workflow_dispatch` and committing `.llm-fuzz/cases/*.jsonl` like any other test
fixture.

## Optional extras

`skills/` holds an agent skill you can install in your own editor to help write
the marked tests before you ever run the action. It suggests which functions are
worth fuzzing and what invariants to assert. Nothing here needs it — the action
does not read it, and everything above works without it. `skills/SKILL.md` is
the Claude Code format, `skills/openai.yaml` the OpenAI one.

## TODO

- Node/Vitest support
- Declare fuzzed parameters on the marker, so malformed agent output is
  impossible rather than merely survivable
- Enforce `budget_usd` on Codex
- SARIF output
