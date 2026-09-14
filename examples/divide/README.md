# Divide Example

This example demonstrates testing without any LLM credentials by using a saved
input case committed under `.llm-fuzz/cases`.

The function is intentionally vulnerable:

```python
def divide(x, y):
    return x / y
```

The fuzz marker declares the target and its per-test generation budget. The test
harness declares the invariant: `divide` should not leak a raw `ZeroDivisionError`.

Run it from the `llm-fuzz-ci` directory:

```bash
python -m pip install -e .
llm-fuzz-ci collect examples/divide --output examples/divide/.llm-fuzz/targets.json
llm-fuzz-ci cases --corpus-dir examples/divide/.llm-fuzz/cases
llm-fuzz-ci test-fuzz-cases --corpus-dir examples/divide/.llm-fuzz/cases --report examples/divide/.llm-fuzz/reports/test-report.json --require-cases -- examples/divide -q
```

The test command should fail because the saved input case uses
`{"x": 1, "y": 0}`.

To make it pass, change `app.py` to:

```python
def divide(x, y):
    if y == 0:
        return None
    return x / y
```

Then rerun the test command.
