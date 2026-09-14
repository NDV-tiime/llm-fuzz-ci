import json
import re
from urllib.parse import urlparse

import pytest

from demo_codebase.auth import has_required_scope
from demo_codebase.exports import BASE_EXPORT_DIR, build_export_path, normalize_tenant_id
from demo_codebase.profile_cards import render_profile_card
from demo_codebase.prompts import build_support_prompt
from demo_codebase.redirects import TRUSTED_HOST, normalize_return_url
from demo_codebase.search import build_customer_search_query
from demo_codebase.webhooks import sign_raw_body, verify_payment_webhook


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_payment_webhook_signature_uses_exact_raw_body(llm_fuzz_case):
    """Payment webhook HMAC verification must bind to the exact raw request body."""
    received_body = llm_fuzz_case.input["received_body"]
    if not isinstance(received_body, str):
        return

    try:
        parsed = json.loads(received_body)
    except json.JSONDecodeError:
        return
    if not isinstance(parsed, dict):
        return

    canonical_body = json.dumps(parsed, separators=(",", ":"), sort_keys=True)
    if received_body != canonical_body:
        signature_for_other_bytes = sign_raw_body(canonical_body)
        assert verify_payment_webhook(received_body, signature_for_other_bytes) is False


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_support_prompt_preserves_message_boundary(llm_fuzz_case):
    """Customer text must stay inside the customer_message prompt section."""
    data = llm_fuzz_case.input
    if not isinstance(data.get("customer_message"), str):
        return
    if not isinstance(data.get("account_tier", "standard"), str):
        return

    prompt = build_support_prompt(data["customer_message"], data.get("account_tier", "standard"))

    assert prompt.count("<system>") == 1
    assert prompt.count("</system>") == 1
    assert prompt.count("<customer_message>") == 1
    assert prompt.count("</customer_message>") == 1
    customer_section = prompt.split("<customer_message>", 1)[1]
    assert "<tool_call" not in customer_section.lower()
    assert "<developer" not in customer_section.lower()


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_export_path_stays_under_exact_tenant_directory(llm_fuzz_case):
    """Tenant export paths must stay under the exact normalized tenant directory."""
    data = llm_fuzz_case.input
    if not isinstance(data.get("tenant_id"), str):
        return
    if not isinstance(data.get("filename"), str):
        return

    tenant_root = (BASE_EXPORT_DIR / normalize_tenant_id(data["tenant_id"])).resolve()
    resolved_path = build_export_path(data["tenant_id"], data["filename"]).resolve()

    assert resolved_path == tenant_root or tenant_root in resolved_path.parents


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_customer_search_constrains_order_by_direction(llm_fuzz_case):
    """Search query construction must constrain ORDER BY direction to ASC or DESC."""
    data = llm_fuzz_case.input
    if not all(isinstance(data.get(name), str) for name in ("term", "sort", "direction")):
        return

    query = build_customer_search_query(
        data.get("term", ""),
        data.get("sort", "created_at"),
        data.get("direction", "desc"),
    )
    order_clause = query.split(" ORDER BY ", 1)[1]

    assert re.fullmatch(
        r"(email|created_at|last_login_at) (ASC|DESC) LIMIT 50",
        order_clause,
    )


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_profile_card_keeps_avatar_url_inside_src_attribute(llm_fuzz_case):
    """Profile rendering must keep avatar URLs inside one escaped src attribute."""
    data = llm_fuzz_case.input
    if not isinstance(data.get("avatar_url"), str):
        return
    if not isinstance(data.get("display_name", "Ada"), str):
        return

    html = render_profile_card(data.get("display_name", "Ada"), data["avatar_url"])
    lowered = html.lower()

    assert "<script" not in lowered
    assert "javascript:" not in lowered
    assert " onerror=" not in lowered
    assert " onload=" not in lowered
    assert re.search(r'<img src="[^"]+" alt="[^"]+">', html)


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_login_return_url_allows_only_real_trusted_hosts(llm_fuzz_case):
    """Post-login redirects may target app.example.com or real subdomains only."""
    if not isinstance(llm_fuzz_case.input.get("return_to"), str):
        return

    location = normalize_return_url(llm_fuzz_case.input["return_to"])
    parsed = urlparse(location)
    if parsed.netloc:
        host = parsed.hostname or ""
        assert host == TRUSTED_HOST or host.endswith("." + TRUSTED_HOST)


@pytest.mark.llm_fuzz(budget_usd=0.25)
def test_api_token_scope_requires_exact_or_explicit_wildcard(llm_fuzz_case):
    """OAuth-style scopes require exact matching unless an explicit wildcard grants access."""
    data = llm_fuzz_case.input
    if not isinstance(data.get("granted_scopes"), str):
        return
    if not isinstance(data.get("required_scope"), str):
        return

    granted_scopes = data.get("granted_scopes", "")
    required_scope = data.get("required_scope", "").strip().lower()

    if not _explicitly_allows(granted_scopes, required_scope):
        assert has_required_scope(granted_scopes, required_scope) is False


def _explicitly_allows(granted_scopes: str, required_scope: str) -> bool:
    scopes = {
        scope.strip().lower()
        for scope in granted_scopes.replace(",", " ").split()
        if scope.strip()
    }
    if "*" in scopes:
        return True
    if required_scope in scopes:
        return True
    return any(
        scope.endswith(":*") and required_scope.startswith(scope[:-1])
        for scope in scopes
    )
