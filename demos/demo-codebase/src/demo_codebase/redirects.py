from urllib.parse import urlparse


TRUSTED_HOST = "app.example.com"


def normalize_return_url(return_to: str) -> str:
    """Return a safe post-login redirect target.

    Bug: hostname validation uses suffix matching without a label boundary, so
    ``evilapp.example.com`` is trusted as if it were ``app.example.com``.
    """
    parsed = urlparse(return_to)
    if not parsed.netloc:
        return return_to if return_to.startswith("/") else "/dashboard"
    if parsed.netloc.lower().endswith(TRUSTED_HOST):
        return return_to
    return "/dashboard"
