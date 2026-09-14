def has_required_scope(granted_scopes: str, required_scope: str) -> bool:
    """Return whether an API token grants a required OAuth-style scope.

    Bug: all scopes are treated like prefixes, so a token with ``admin`` can
    satisfy ``admin:delete`` even though only ``admin:*`` should do that.
    """
    required = required_scope.strip().lower()
    scopes = {
        scope.strip().lower()
        for scope in granted_scopes.replace(",", " ").split()
        if scope.strip()
    }
    if "*" in scopes:
        return True
    return any(required.startswith(scope.rstrip("*")) for scope in scopes)
