import re

READ_ONLY_DISALLOWED_KEYWORDS = [
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "DROP",
    "REMOVE",
    "CALL dbms",
]


def ensure_read_only(query: str) -> None:
    normalized = _normalize_query(query)
    upper = normalized.upper()

    if ";" in normalized:
        raise ValueError("Multiple statements are not allowed in read-only mode.")

    for token in READ_ONLY_DISALLOWED_KEYWORDS:
        if token in upper:
            raise ValueError(f"Disallowed keyword in read-only mode: {token}")


def ensure_limit(query: str, max_rows: int) -> str:
    if " LIMIT " in query.upper():
        return query
    return f"{query.rstrip().rstrip(';')} LIMIT {max_rows}"


def _normalize_query(query: str) -> str:
    # Strip inline and block comments to make keyword checks harder to bypass.
    without_inline = re.sub(r"//.*?$", "", query, flags=re.MULTILINE)
    without_block = re.sub(r"/\*.*?\*/", "", without_inline, flags=re.DOTALL)
    return without_block.strip()
