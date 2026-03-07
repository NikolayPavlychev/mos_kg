from app.core.config import get_settings
from app.db.neo4j_client import Neo4jClient
from app.services.query_guard import ensure_limit, ensure_read_only


class QueryService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = Neo4jClient()

    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        ensure_read_only(query)
        safe_query = ensure_limit(query, self._settings.app_cypher_max_rows)
        return self._client.run_read(
            query=safe_query,
            params=params or {},
            timeout_s=self._settings.app_cypher_timeout_seconds,
        )

    def close(self) -> None:
        self._client.close()
