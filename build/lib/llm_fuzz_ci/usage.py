from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .schema import utc_now


@dataclass
class LLMUsage:
    provider: str
    model: str | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    def add(self, other: "LLMUsage") -> None:
        self.input_tokens += other.input_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.output_tokens += other.output_tokens
        self.reasoning_output_tokens += other.reasoning_output_tokens
        self.total_tokens += other.total_tokens

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def format_usage_summary(usage: LLMUsage | None) -> str:
    if usage is None:
        return "LLM token usage: unavailable because the agent did not emit usage metadata."

    lines = [
        "LLM token usage:",
        f"  provider: {usage.provider}",
    ]
    if usage.model:
        lines.append(f"  model: {usage.model}")
    lines.extend(
        [
            f"  input tokens: {usage.input_tokens}",
            f"  cached input tokens: {usage.cached_input_tokens}",
            f"  output tokens: {usage.output_tokens}",
            f"  reasoning output tokens: {usage.reasoning_output_tokens}",
            f"  total tokens: {usage.total_tokens}",
        ]
    )
    return "\n".join(lines)


def write_usage_report(
    path: str | Path,
    *,
    agent: str,
    model: str | None,
    provider: str | None,
    target_count: int,
    case_count: int,
    usage: LLMUsage | None,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "llm-fuzz.usage.v1",
        "generated_at": utc_now(),
        "agent": agent,
        "provider": provider,
        "model": model,
        "target_count": target_count,
        "case_count": case_count,
        "usage": usage.to_dict() if usage else None,
    }
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return output


def extract_usage_from_json_events(
    text: str,
    *,
    provider: str,
    model: str | None,
) -> LLMUsage | None:
    usage = LLMUsage(provider=provider, model=model)
    found_usage = False

    for obj in _iter_json_objects(text):
        for usage_data in _find_usage_dicts(obj):
            extracted = _usage_from_dict(usage_data, provider=provider, model=model)
            if extracted is None:
                continue
            usage.add(extracted)
            found_usage = True

    if not found_usage:
        return None
    if usage.total_tokens == 0:
        usage.total_tokens = usage.input_tokens + usage.output_tokens
    return usage


def _usage_from_dict(data: dict[str, Any], *, provider: str, model: str | None) -> LLMUsage | None:
    input_tokens = _int_value(data, "input_tokens")
    output_tokens = _int_value(data, "output_tokens")
    cached_input_tokens = _int_value(data, "cached_input_tokens")
    reasoning_output_tokens = _int_value(data, "reasoning_output_tokens")
    total_tokens = _int_value(data, "total_tokens")

    # Claude-style cache fields are common in JSON summaries. Treat cache reads
    # as cached input; cache creation is still ordinary input token usage.
    cached_input_tokens += _int_value(data, "cache_read_input_tokens")
    input_tokens += _int_value(data, "cache_creation_input_tokens")

    details = data.get("input_tokens_details")
    if isinstance(details, dict):
        cached_input_tokens += _int_value(details, "cached_tokens")

    output_details = data.get("output_tokens_details")
    if isinstance(output_details, dict):
        reasoning_output_tokens += _int_value(output_details, "reasoning_tokens")

    if not any((input_tokens, output_tokens, cached_input_tokens, reasoning_output_tokens, total_tokens)):
        return None

    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens

    return LLMUsage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
    )


def _iter_json_objects(text: str) -> list[Any]:
    stripped = text.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
        return [parsed]
    except json.JSONDecodeError:
        pass

    objects: list[Any] = []
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            objects.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return objects


def _find_usage_dicts(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        usage = value.get("usage")
        if isinstance(usage, dict):
            found.append(usage)
        for child in value.values():
            found.extend(_find_usage_dicts(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_usage_dicts(child))
    return found


def _int_value(data: dict[str, Any], key: str) -> int:
    value = data.get(key, 0)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
