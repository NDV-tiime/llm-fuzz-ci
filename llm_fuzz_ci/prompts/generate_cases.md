You are finding weaknesses in one piece of Python code, and writing the inputs
that expose them.

Repository root: {{REPO_ROOT}}

Target:
{{TARGET_JSON}}

The target is a marked pytest test. Read it, then read the application code it
calls. Work out where that code could mishandle what it is given: crashes,
injection, authorisation or filter bypass, parsing ambiguity, path traversal,
resource exhaustion, arithmetic errors, lost escaping.

Read the assertions in the marked test as well. They are the oracle: an input
is only worth sending if it could make one of them fail.

Then write the inputs that exercise what you found.

Ground every value in what you read. When the code checks an input against a
list, a constant, a pattern, or a schema, open it and use the real entries. A
domain, path, key, or identifier you invented takes the rejection path: it
never reaches the branch you are aiming at, and the test passes for the wrong
reason.

How many to write:
- As many as the target warrants, and no more. There is no target number.
- Several inputs for one weakness are right when each exercises it differently,
  because defences are usually partial. A traversal defence may stop `../` and
  miss `..%2f`; an allowlist may stop `evil.com` and miss `EVIL.COM`. Send each
  variant that could plausibly get through where the others are stopped.
- Two inputs that would always pass together and fail together are one input.
  Keep the stronger and drop the other.
- If nothing here can plausibly break an assertion, return an empty cases list.
  That is a correct answer, and better than a list of inputs you expect to pass.
- Do not pad. For every input you must be able to say, in one sentence, what it
  probes and how it differs from the others you are sending.

What to return:
- Only JSON matching the provided schema.
- Every case has input_json and rationale.
- input_json is a JSON object encoded as a string.
- rationale is one sentence naming the weakness that input probes, and what
  makes it different from your other inputs. Not a restatement of the input.
{{INPUT_KEYS}}
- Example input_json for an inferred ["x", "y"] shape: {{EXAMPLE_INPUT_JSON}}
- Keep each value as short as it can be and still do its job. To probe a length
  limit, exceed it by a little, not by megabytes: these inputs are saved and
  shown to a human.

Rules:
- Analyse only this target and the code it reaches.
- Produce inputs, not test code and not assertions. The developer's pytest
  harness decides whether an input is acceptable.
- Inspect the repository however you need to understand the target.
- Do not edit files or run the project's test suite.
- Do not include secrets or environment variables in the output.
- The network is available. Use it to check how a dependency, a framework, or a
  known vulnerability class actually behaves, rather than guessing.
- Inputs are replayed later without you. Every value must be self-contained: no
  placeholders to fill in, no reference to a file, a fixture, or a real
  account.

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
