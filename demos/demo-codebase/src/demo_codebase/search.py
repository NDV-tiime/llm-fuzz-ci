ALLOWED_SORT_COLUMNS = {
    "email": "email",
    "created_at": "created_at",
    "last_login": "last_login_at",
}


def build_customer_search_query(
    term: str,
    sort: str = "created_at",
    direction: str = "desc",
) -> str:
    """Build a SQL query for customer support search.

    Bug: the search term and sort column are normalized, but the ORDER BY
    direction is copied into SQL directly.
    """
    escaped_term = term.replace("'", "''")
    sort_column = ALLOWED_SORT_COLUMNS.get(sort, "created_at")
    sort_direction = direction.strip().upper() or "DESC"
    return (
        "SELECT id, email FROM customers "
        f"WHERE email LIKE '%{escaped_term}%' "
        f"ORDER BY {sort_column} {sort_direction} LIMIT 50"
    )
