from pathlib import Path
import re


BASE_EXPORT_DIR = Path("/srv/demo-codebase/exports")
TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def normalize_tenant_id(tenant_id: str) -> str:
    cleaned = tenant_id.strip().lower()
    return cleaned if TENANT_RE.fullmatch(cleaned) else "public"


def build_export_path(tenant_id: str, filename: str) -> Path:
    """Build the path where a tenant export file will be written.

    Bug: the safety check uses string prefix matching, so sibling directories
    such as ``tenant-audit`` can pass checks for tenant ``tenant``.
    """
    tenant = normalize_tenant_id(tenant_id)
    tenant_root = (BASE_EXPORT_DIR / tenant).resolve()
    requested = (tenant_root / filename).resolve()
    if str(requested).startswith(str(tenant_root)):
        return requested
    return tenant_root / "blocked.csv"
