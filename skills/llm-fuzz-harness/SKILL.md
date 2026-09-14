---
name: llm-fuzz-harness
description: Create or update developer-owned LLM Fuzz CI harness tests with pytest markers and deterministic security assertions. Use when asked to add LLM Fuzz coverage to Python functions, identify functions worth fuzzing, write the test wrappers/invariants that consume llm_fuzz_case, or prepare a repository for the LLM Fuzz GitHub Action. Do not use this skill to generate saved fuzz inputs or generated assertion code.
---

# LLM Fuzz Harness

## Overview

Create normal pytest tests that declare LLM Fuzz CI targets and assert security invariants. The CI generator later creates saved fuzz inputs for those marked tests; this skill must not generate fuzz input files or let generated assertions decide CI pass/fail.

## Workflow

1. Inspect the repository test style and existing fixtures before adding tests.
2. Identify functions that handle untrusted or ambiguous input: request parsing, URL/path handling, auth decisions, template rendering, command construction, prompt/LLM calls, deserialization, numeric boundaries, file access, or database query construction.
3. Add or update pytest tests using `@pytest.mark.llm_fuzz(budget_usd=...)`.
4. Write a harness that calls the real function with `llm_fuzz_case.input`.
5. Assert deterministic security invariants owned by the developer/test suite.
6. Run the focused tests locally when possible.

## Required Pattern

Use this marker shape:

```python
@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_function_security_invariant(llm_fuzz_case):
    result = function_name(**llm_fuzz_case.input)
    assert ...
```

Guidance:

- `budget_usd` is required and belongs to that marked test.
- LLM Fuzz CI derives the target id from the pytest node id.
- The generator infers input keys from `llm_fuzz_case.input` usages and the real code called by the test.
- Put security intent in the test name, assertions, and an optional Python docstring.
- Configure only the per-test generation budget in the marker.
- Keep tests in the repository's normal test tree.

## Assertion Rules

Write assertions manually in the test. Do not ask LLM Fuzz CI to generate assertions. Do not write tests that merely check type or non-null output unless that is the actual security invariant.

Prefer invariants such as:

- The function rejects or sanitizes invalid input without raw crashes.
- The output remains inside an allowlisted domain, directory, role, or schema.
- Sensitive strings, prompts, secrets, stack traces, internal IDs, or privileged tool outputs are not disclosed.
- Authorization decisions cannot become `True` from malformed input.
- Generated SQL, shell commands, file paths, URLs, HTML, raw request bodies, or prompts preserve escaping and boundaries.
- LLM-facing responses do not reveal hidden instructions and do not follow attacker-injected instructions.

Avoid:

- Executing LLM-generated assertion code.
- Committing generated fuzz inputs while creating the harness, unless the user explicitly asks.
- Making brittle keyword checks unrelated to a concrete policy.
- Swallowing all exceptions as success.
- Calling real external services from generated-input tests unless the project already has isolated fixtures/mocks.

## Examples

Numeric boundary:

```python
@pytest.mark.llm_fuzz(budget_usd=0.05)
def test_divide_fuzz(llm_fuzz_case):
    """Division must not leak raw ZeroDivisionError for user-supplied numbers."""
    try:
        result = divide(**llm_fuzz_case.input)
    except ZeroDivisionError:
        pytest.fail("divide should handle y=0 before Python raises ZeroDivisionError")

    assert result is None or isinstance(result, (int, float))
```

Prompt-injection boundary:

```python
@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_support_agent_prompt_injection(llm_fuzz_case, fake_llm, fake_tools):
    """User messages must not reveal hidden instructions, secrets, or tool configuration."""
    response = answer_support_question(llm_fuzz_case.input["message"])

    forbidden = [
        "system prompt",
        "developer message",
        "OPENAI_API_KEY",
        "internal tool",
        "hidden instruction",
    ]
    assert all(term.lower() not in response.lower() for term in forbidden)
    assert "I cannot" in response or "support" in response.lower()
```

## Final Check

Before finishing, report which tests were marked and what each assertion protects. Remind the user to run `llm-fuzz-ci collect`, `llm-fuzz-ci generate`, `llm-fuzz-ci cases`, and `llm-fuzz-ci test-fuzz-cases` after installing LLM Fuzz CI.
