You are generating saved fuzz cases for LLM Fuzz CI.

Repository root: {{REPO_ROOT}}

Targets:
{{TARGETS_JSON}}

Rules:
- Analyze only the listed targets and their reachable helpers.
- Produce adversarial inputs, not executable test code or assertions.
- Return only JSON that matches the provided schema.
- Every case must include input_json and rationale.
- Every case.input_json value must be a valid JSON object encoded as a string.
- rationale is one sentence saying what weakness the input probes.
- Every target includes budget_usd. Generate the best cases you can for that target within that budget.
- Infer the input_json keys from the marked pytest harness, especially llm_fuzz_case.input access patterns and calls made by the test.
- Example input_json for an inferred ["x", "y"] shape: {{EXAMPLE_INPUT_JSON}}
- Generate at most target.max_cases cases per target.
- Prefer cases that can expose crashes, injection, auth bypass, parsing ambiguity, path traversal, resource exhaustion, or arithmetic errors.
- You may inspect source files and run lightweight read-only inspection commands when the agent runtime allows it.
- Do not describe pass/fail assertions. The developer's pytest/Vitest harness owns those invariants.
- Do not edit files.
- Do not run the project's test suite.
- Do not perform network requests or web searches unless the agent runtime explicitly enables them and the result is needed to understand a dependency, framework, or vulnerability class.
- Do not include secrets or environment variables in the output.

Input guidance:
- Use each target's id, source code, and description to infer the relevant attack families.
- When target.target starts with `pytest::`, treat the marked pytest test as the target harness and analyze the application code it calls.
- For webhook or signature validation, include valid JSON objects whose raw bytes differ from compact sorted JSON, such as whitespace, reordered keys, unicode escapes, or duplicate keys.
- For LLM/prompt boundaries, include messages that close XML/JSON/Markdown prompt delimiters and introduce system, developer, or tool sections.
- For path handling, include parent-directory, absolute-path, encoded traversal, and sibling-directory prefix variants.
- For SQL construction, include quotes, comments, statement terminators, stacked-query attempts, and ASC/DESC direction payloads.
- For HTML rendering, include script tags, event handlers, quote-breaking attribute payloads, data URLs, and javascript: URLs.
- For redirects and URL validation, include //host network-path references, userinfo tricks, suffix confusion, ports, mixed casing, and encoded hostnames.
- For authorization, include exact-match bypasses, prefix scopes, wildcard-like strings, and privileged child scopes.

The caller's pytest/Vitest harness will decide whether a case is acceptable.
