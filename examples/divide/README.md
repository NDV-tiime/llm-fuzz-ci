# divide

A two-line function with an unguarded division, one marked test, and two
generated inputs committed under `.llm-fuzz/cases`. No API key needed.

From the repository root:

```bash
python -m pip install -e .

llm-fuzz-ci test-fuzz-cases \
  --corpus-dir examples/divide/.llm-fuzz/cases \
  --report /tmp/test-report.json \
  --require-cases -- examples/divide -q

llm-fuzz-ci summary \
  --corpus-dir examples/divide/.llm-fuzz/cases \
  --report /tmp/test-report.json \
  --output /tmp/report.md && cat /tmp/report.md
```

One input passes, one fails. Guard the divisor in `app.py` and both pass:

```python
def divide(x, y):
    if y == 0:
        return None
    return x / y
```
