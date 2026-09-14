# Demo Codebase

This folder simulates a normal user repository that installed LLM Fuzz CI.

It contains intentionally vulnerable but realistic service utilities and
developer-owned pytest harnesses that declare fuzz targets and per-test budgets.
The generator creates inputs only; the assertions live in
`tests/test_security_fuzz.py`.

## Vulnerabilities Demonstrated

- Webhook signatures: the verifier signs canonical JSON instead of the exact raw request body.
- Prompt boundaries: customer text can close XML-like prompt sections and inject privileged sections.
- Tenant exports: path validation uses unsafe string-prefix checks for resolved paths.
- SQL ordering: the search term is escaped, but the `ORDER BY` direction is still interpolated.
- HTML attributes: trusted-looking avatar URLs are not escaped before entering an attribute.
- Login redirects: hostname suffix matching trusts `evilapp.example.com`.
- API scopes: OAuth-style scope checks treat bare prefixes as if they were explicit wildcards.

## Run It Like CI, Locally

From the LLM Fuzz CI project root, install the action package and then run the
demo repo exactly like a checked-out project:

```bash
cd /Users/utilisateur/Documents/LLM/llm-fuzz/llm-fuzz-ci
python -m pip install -e .
cd demos/demo-codebase
python -m pip install -e .
git init
git add .

curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
export PATH="$HOME/.local/bin:$PATH"
hash -r 2>/dev/null || rehash 2>/dev/null || true
command -v codex
codex --version
codex exec --help

export CODEX_API_KEY="sk-replace-me"
llm-fuzz-ci collect tests --output .llm-fuzz/targets.json
llm-fuzz-ci generate \
  --agent codex \
  --model gpt-5.6-terra \
  --targets .llm-fuzz/targets.json \
  --corpus-dir .llm-fuzz/cases \
  --show-usage \
  --usage-report .llm-fuzz/reports/llm-usage.json
llm-fuzz-ci cases --corpus-dir .llm-fuzz/cases
llm-fuzz-ci test-fuzz-cases --corpus-dir .llm-fuzz/cases --report .llm-fuzz/reports/test-report.json --require-cases -- tests -q
```

Replace `sk-replace-me` with a real key. Generation should print total LLM token
usage and write `.llm-fuzz/reports/llm-usage.json`; testing should fail and
write `.llm-fuzz/reports/test-report.json`.

The generation step above calls the real Codex CLI. No canned fuzz cases are
included in this demo.

Render the test results in a readable terminal format:

```bash
llm-fuzz-ci report \
  --report .llm-fuzz/reports/test-report.json \
  --all \
  --show-failure-details
```

Write a Markdown report that is easier to inspect in an editor or CI artifact:

```bash
llm-fuzz-ci report \
  --report .llm-fuzz/reports/test-report.json \
  --format markdown \
  --all \
  --show-failure-details \
  --output .llm-fuzz/reports/test-report.md
```

Preview the GitHub issue alert body. It includes only the generated inputs that
actually failed the test assertions:

```bash
llm-fuzz-ci alert github-issue \
  --report .llm-fuzz/reports/test-report.json \
  --repo your-org/demo-codebase \
  --dry-run
```

## Run With Codex In GitHub Actions

Use the split workflow in `.github/workflows/llm-fuzz.yml` and create this
repository secret:

```text
OPENAI_API_KEY=sk-replace-me
```

The first job uses `llm-fuzz-ci/actions/generate` to create `.llm-fuzz/cases` as
an artifact. The second job installs the pytest plugin and tests those inputs
with ordinary test commands, then uses `actions/github-script` to create an
issue if a generated input fails.

Keep application secrets in the test job. The generation job should need
only the LLM provider key.

For a local Codex run, replace the placeholder and run:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=1 sh
export PATH="$HOME/.local/bin:$PATH"
hash -r 2>/dev/null || rehash 2>/dev/null || true
command -v codex
codex --version
codex exec --help

export CODEX_API_KEY="sk-replace-me"
llm-fuzz-ci collect tests --output .llm-fuzz/targets.json
llm-fuzz-ci generate \
  --agent codex \
  --model gpt-5.6-terra \
  --targets .llm-fuzz/targets.json \
  --corpus-dir .llm-fuzz/cases \
  --show-usage \
  --usage-report .llm-fuzz/reports/llm-usage.json
llm-fuzz-ci cases --corpus-dir .llm-fuzz/cases
llm-fuzz-ci test-fuzz-cases --corpus-dir .llm-fuzz/cases --report .llm-fuzz/reports/test-report.json --require-cases -- tests -q
```

If `codex exec --help` prints only the old top-level Codex help, update your
PATH so the newly installed Codex CLI is used before the older npm-era binary.

For OpenRouter through Codex:

```bash
export OPENROUTER_API_KEY="sk-or-replace-me"
llm-fuzz-ci generate \
  --agent codex \
  --provider openrouter \
  --model "<openrouter-model-slug>" \
  --targets .llm-fuzz/targets.json \
  --corpus-dir .llm-fuzz/cases \
  --show-usage \
  --usage-report .llm-fuzz/reports/llm-usage.json
```

For Claude Code:

```bash
export ANTHROPIC_API_KEY="sk-ant-replace-me"
llm-fuzz-ci generate \
  --agent claude \
  --model sonnet \
  --max-turns 8 \
  --max-budget-usd 1.00 \
  --targets .llm-fuzz/targets.json \
  --corpus-dir .llm-fuzz/cases \
  --show-usage \
  --usage-report .llm-fuzz/reports/llm-usage.json
```

`--max-budget-usd` is optional here; it overrides the budgets declared on the
markers for this one run.
