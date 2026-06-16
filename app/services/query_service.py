import logging
import time

from app.core.config import get_settings
from app.db.neo4j_client import Neo4jClient
from app.services.query_guard import ensure_limit, ensure_read_only

logger = logging.getLogger(__name__)


class QueryService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = Neo4jClient()

    def run_cypher(self, query: str, params: dict | None = None) -> list[dict]:
        logger.debug(
            "Executing Cypher query",
            extra={"query": query, "params": params},
        )

        ensure_read_only(query)
        safe_query = ensure_limit(query, self._settings.app_cypher_max_rows)

        start_time = time.monotonic()
        try:
            result = self._client.run_read(
                query=safe_query,
                params=params or {},
                timeout_s=self._settings.app_cypher_timeout_seconds,
            )
            duration_ms = (time.monotonic() - start_time) * 1000

            logger.info(
                "Cypher query executed successfully",
                extra={
                    "row_count": len(result),
                    "duration_ms": round(duration_ms, 2),
                    "query_preview": query[:100],
                },
            )
            return result
        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Cypher query failed",
                extra={
                    "error": str(exc),
                    "duration_ms": round(duration_ms, 2),
                    "query_preview": query[:100],
                },
                exc_info=True,
            )
            raise

    def close(self) -> None:
        self._client.close()
