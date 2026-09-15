You are finding weaknesses in one piece of Python code, and writing the inputs
that expose them.

Repository root: {{REPO_ROOT}}

Target:
{{TARGET_JSON}}

The target is a marked pytest test. Read it, then read the application code it
calls. Work out where that code could mishandle what it is given: crashes,
injection, authorisation or filter bypass, parsing ambiguity, path traversal,
resource exhaustion, arithmetic errors, lost escaping.

Then write one input for each weakness you found.

How many to write:
- One input per distinct weakness. Two inputs that probe the same weakness with
  different values are one weakness, not two.
- If you find nothing, return an empty cases list. That is a correct answer.
- Never pad the list to look thorough. If you cannot name what an input probes
  in one specific sentence, it does not belong.
- A small set of sharp inputs is worth more than a long list of variations.

What to return:
- Only JSON matching the provided schema.
- Every case has input_json and rationale.
- input_json is a JSON object encoded as a string.
- rationale is one sentence naming the weakness that input probes. Not a
  restatement of the input.
{{INPUT_KEYS}}
- Example input_json for an inferred ["x", "y"] shape: {{EXAMPLE_INPUT_JSON}}

Rules:
- Analyse only this target and the code it reaches.
- Produce inputs, not test code and not assertions. The developer's pytest
  harness decides whether an input is acceptable.
- Inspect the repository however you need to understand the target.
- Do not edit files or run the project's test suite.
- Do not include secrets or environment variables in the output.
- Do not make network requests unless one is needed to understand a dependency,
  framework, or vulnerability class.

Where weaknesses usually are:
- Webhook or signature validation: JSON whose raw bytes differ from compact
  sorted JSON, through whitespace, reordered keys, unicode escapes, or
  duplicate keys.
- Prompt boundaries: text that closes XML, JSON or Markdown delimiters and
  opens a system, developer, or tool section of its own.
- Path handling: parent-directory, absolute-path, encoded traversal, and
  sibling-directory prefix variants.
- SQL construction: quotes, comments, statement terminators, stacked queries,
  and ordering-direction payloads.
- HTML rendering: script tags, event handlers, quote-breaking attribute
  payloads, data URLs, javascript: URLs.
- Redirects and URL validation: //host network-path references, userinfo
  tricks, suffix confusion, ports, mixed casing, encoded hostnames.
- Authorisation: exact-match bypasses, prefix scopes, wildcard-like strings,
  privileged child scopes.
- Type and absence: null, wrong type, empty, and missing where the code assumes
  a populated string.
