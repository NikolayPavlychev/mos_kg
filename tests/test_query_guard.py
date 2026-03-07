import pytest

from app.services.query_guard import ensure_limit, ensure_read_only


def test_ensure_read_only_blocks_write() -> None:
    with pytest.raises(ValueError):
        ensure_read_only("MATCH (n) DELETE n")


def test_ensure_read_only_blocks_multiple_statements() -> None:
    with pytest.raises(ValueError):
        ensure_read_only("MATCH (n) RETURN n; MATCH (m) RETURN m")


def test_ensure_limit_adds_limit() -> None:
    query = "MATCH (d:District) RETURN d.name AS name"
    guarded = ensure_limit(query, max_rows=25)
    assert guarded.endswith("LIMIT 25")
