import json

from llm_fuzz_ci.usage import (
    extract_usage_from_json_events,
    format_usage_summary,
    write_usage_report,
)


def test_extracts_codex_jsonl_token_usage():
    text = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "abc"}),
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 1200,
                        "cached_input_tokens": 500,
                        "output_tokens": 300,
                        "reasoning_output_tokens": 90,
                    },
                }
            ),
        ]
    )

    usage = extract_usage_from_json_events(text, provider="openai", model="gpt-test")

    assert usage is not None
    assert usage.input_tokens == 1200
    assert usage.cached_input_tokens == 500
    assert usage.output_tokens == 300
    assert usage.reasoning_output_tokens == 90
    assert usage.total_tokens == 1500


def test_extracts_claude_style_token_usage():
    text = json.dumps(
        {
            "type": "result",
            "usage": {
                "input_tokens": 100,
                "cache_creation_input_tokens": 40,
                "cache_read_input_tokens": 60,
                "output_tokens": 25,
            },
        }
    )

    usage = extract_usage_from_json_events(text, provider="anthropic", model="sonnet")

    assert usage is not None
    assert usage.input_tokens == 140
    assert usage.cached_input_tokens == 60
    assert usage.output_tokens == 25
    assert usage.total_tokens == 165


def test_usage_summary_and_report_are_token_only(tmp_path):
    usage = extract_usage_from_json_events(
        json.dumps({"usage": {"input_tokens": 10, "output_tokens": 5}}),
        provider="openai",
        model="gpt-test",
    )

    summary = format_usage_summary(usage)
    path = write_usage_report(
        tmp_path / "usage.json",
        agent="codex",
        model="gpt-test",
        provider="openai",
        target_count=1,
        case_count=2,
        usage=usage,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert "cost" not in summary.lower()
    assert "usage" in payload
    assert payload["provider"] == "openai"
    assert "cost" not in json.dumps(payload).lower()
