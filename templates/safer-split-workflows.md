# Safer CI Deployment Pattern

Recommended production shape:

1. `llm-fuzz-ci/actions/generate` runs the coding agent and writes JSONL input cases.
2. `actions/upload-artifact` stores those input files as ordinary data.
3. The normal test job installs the pytest plugin and tests those inputs with pytest.
4. Alerting is handled by existing GitHub Actions or `gh`, not by a custom test action.

This keeps the agent away from the environment that executes the project's full
test/runtime setup. The generation job still receives the LLM provider key, so
use a least-privilege, budget-limited key and do not expose application/runtime
secrets in that job.

## One-Call Reusable Workflow

Use this when you want a minimal setup in the caller repository while preserving
separate generation and test jobs:

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

Do not use a composite action for all-in-one generation plus testing if you need
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

      - name: Show generated inputs
        run: |
          llm-fuzz-ci cases \
            --corpus-dir .llm-fuzz/cases \
            --output .llm-fuzz/reports/generated-inputs.md
          cat .llm-fuzz/reports/generated-inputs.md
          cat .llm-fuzz/reports/generated-inputs.md >> "$GITHUB_STEP_SUMMARY"

      - uses: actions/upload-artifact@v7
        with:
          name: llm-fuzz-cases
          path: |
            .llm-fuzz/targets.json
            .llm-fuzz/cases
            .llm-fuzz/reports
          if-no-files-found: error

  test-fuzz-cases:
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

      - name: Test fuzz cases
        id: test_fuzz_cases
        continue-on-error: true
        env:
          PYTHONPATH: src
        run: |
          llm-fuzz-ci test-fuzz-cases \
            --corpus-dir .llm-fuzz/cases \
            --report .llm-fuzz/reports/test-report.json \
            --require-cases \
            -- tests -q

      - name: Show test report
        if: always()
        run: |
          if [ ! -f .llm-fuzz/reports/test-report.json ]; then
            echo "No LLM Fuzz CI test report was produced."
            exit 0
          fi
          llm-fuzz-ci report \
            --report .llm-fuzz/reports/test-report.json \
            --format markdown \
            --all \
            --show-failure-details \
            --output .llm-fuzz/reports/test-report.md
          cat .llm-fuzz/reports/test-report.md
          cat .llm-fuzz/reports/test-report.md >> "$GITHUB_STEP_SUMMARY"

      - name: Write full report artifact
        if: always()
        run: |
          llm-fuzz-ci summary \
            --corpus-dir .llm-fuzz/cases \
            --report .llm-fuzz/reports/test-report.json \
            --usage-report .llm-fuzz/reports/llm-usage.json \
            --output .llm-fuzz/reports/llm-fuzz-ci-report.md

      - name: Upload test report
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: llm-fuzz-test-report
          path: .llm-fuzz/reports
          if-no-files-found: ignore

      - name: Create GitHub issue
        if: steps.test_fuzz_cases.outcome == 'failure'
        uses: actions/github-script@v9
        env:
          REPORT_PATH: .llm-fuzz/reports/test-report.md
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
        if: steps.test_fuzz_cases.outcome == 'failure'
        run: exit 1
```

## Public Repositories

For public repositories, the safest default is even stricter:

- run generation only on `workflow_dispatch`, `schedule`, or trusted branch
  `push`;
- review and commit the generated `.llm-fuzz/cases/*.jsonl` files like test
  fixtures;
- run only the test job on untrusted pull requests, with no LLM API secrets.

Avoid `pull_request_target` for any workflow that checks out and executes pull
request code with secrets.
