from __future__ import annotations

import hashlib
import hmac
import json


WEBHOOK_SECRET = b"demo-codebase-webhook-secret"


def sign_raw_body(body: str, *, secret: bytes = WEBHOOK_SECRET) -> str:
    return hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_payment_webhook(
    received_body: str,
    signature: str,
    *,
    secret: bytes = WEBHOOK_SECRET,
) -> bool:
    """Validate the HMAC signature for an incoming payment webhook.

    Bug: the signature is checked against canonicalized JSON, not the exact raw
    request body that the payment provider signed.
    """
    try:
        payload = json.loads(received_body)
    except json.JSONDecodeError:
        return False

    canonical_body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected = sign_raw_body(canonical_body, secret=secret)
    return hmac.compare_digest(expected, signature)
