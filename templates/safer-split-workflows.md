# Safer CI Deployment Pattern

Recommended production shape:

1. `llm-fuzz-ci/actions/generate` runs the coding agent and writes JSONL input cases.
2. `actions/upload-artifact` stores those input files as ordinary data.
3. The normal test job installs the pytest plugin and runs replay with pytest.
4. Alerting is handled by existing GitHub Actions or `gh`, not by a custom replay action.

This keeps the agent away from the environment that executes the project's full
test/runtime setup. The generation job still receives the LLM provider key, so
use a least-privilege, budget-limited key and do not expose application/runtime
secrets in that job.

## One-Call Reusable Workflow

Use this when you want a minimal setup in the caller repository while preserving
separate generation and replay jobs:

```yaml
jobs:
  llm-fuzz-ci:
    uses: llm-fuzz/llm-fuzz-ci/.github/workflows/llm-fuzz-ci.yml@v1
    permissions:
      contents: read
      issues: write
    with:
      test-paths: tests
      setup-command: |
        python -m pip install -U pip
        python -m pip install -r requirements.txt
        python -m pip install -e .
      pythonpath: src
      agent: codex
      model: gpt-5.6-terra
      show-usage: true
      create-issue: true
    secrets:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

Do not use a composite action for all-in-one generation plus replay if you need
environment isolation. Composite action steps run inside the caller job.

## One Workflow, Two Jobs

Use this for private repositories or trusted pull requests.

```yaml
name: LLM Fuzz CI

on:
  pull_request:
  workflow_dispatch:
  schedule:
    - cron: "17 2 * * *"

jobs:
  generate-fuzz-cases:
    # Do not run LLM-backed generation on untrusted fork PRs with secrets.
    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false

      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - uses: llm-fuzz/llm-fuzz-ci/actions/generate@v1
        with:
          test-paths: tests
          setup-command: |
            python -m pip install -U pip
            python -m pip install -r requirements.txt
            python -m pip install -e .
          pythonpath: src
          agent: codex
          model: gpt-5.6-terra
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          show-usage: "true"
          usage-report: .llm-fuzz/reports/llm-usage.json
          # Set to "true" only if this workflow restores old .llm-fuzz/cases first.
          reuse-existing-cases: "false"

      - uses: actions/upload-artifact@v7
        with:
          name: llm-fuzz-cases
          path: |
            .llm-fuzz/targets.json
            .llm-fuzz/cases
            .llm-fuzz/reports/llm-usage.json
          if-no-files-found: error

  replay-fuzz-cases:
    needs: generate-fuzz-cases
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write

    steps:
      - uses: actions/checkout@v7

      - uses: actions/download-artifact@v8
        with:
          name: llm-fuzz-cases
          path: .

      - uses: actions/setup-python@v7
        with:
          python-version: "3.12"

      - uses: llm-fuzz/llm-fuzz-ci/actions/setup@v1

      - name: Install test dependencies
        run: |
          python -m pip install -U pip
          python -m pip install -r requirements.txt
          python -m pip install -e .

      - name: Replay fuzz cases
        id: replay
        continue-on-error: true
        env:
          PYTHONPATH: src
        run: |
          llm-fuzz-ci replay \
            --corpus-dir .llm-fuzz/cases \
            --report .llm-fuzz/reports/replay-report.json \
            --require-cases \
            -- tests -q

      - name: Render report
        if: steps.replay.outcome == 'failure'
        run: |
          llm-fuzz-ci report \
            --report .llm-fuzz/reports/replay-report.json \
            --format markdown \
            --show-failure-details \
            --output .llm-fuzz/reports/replay-report.md

      - name: Upload replay report
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: llm-fuzz-report
          path: .llm-fuzz/reports
          if-no-files-found: ignore

      - name: Create GitHub issue
        if: steps.replay.outcome == 'failure'
        uses: actions/github-script@v9
        env:
          REPORT_PATH: .llm-fuzz/reports/replay-report.md
        with:
          script: |
            const fs = require('fs');
            const body = fs.readFileSync(process.env.REPORT_PATH, 'utf8');
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: 'LLM Fuzz CI detected a vulnerability',
              body
            });

      - name: Fail workflow
        if: steps.replay.outcome == 'failure'
        run: exit 1
```

## Public Repositories

For public repositories, the safest default is even stricter:

- run generation only on `workflow_dispatch`, `schedule`, or trusted branch
  `push`;
- review and commit the generated `.llm-fuzz/cases/*.jsonl` files like test
  fixtures;
- run only replay on untrusted pull requests, with no LLM API secrets.

Avoid `pull_request_target` for any workflow that checks out and executes pull
request code with secrets.

## Preserving Old Cases

The generation action replaces generated case files by default. To keep old
cases, first restore them into `.llm-fuzz/cases`, then set:

```yaml
reuse-existing-cases: "true"
```

Good persistence options:

- commit reviewed `.llm-fuzz/cases/*.jsonl` files to the repository;
- download a previous workflow artifact before generation;
- sync the corpus from external storage such as S3/GCS/Azure Blob;
- use the GitHub cache only for non-sensitive corpora and with the usual cache
  immutability/security caveats.
