from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

from app.core.config import get_settings


class Neo4jClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )

    def close(self) -> None:
        self._driver.close()

    def run_read(self, query: str, params: dict | None = None, timeout_s: int = 10) -> list[dict]:
        def _tx(tx):
            result = tx.run(query, params or {}, timeout=timeout_s)
            return [record.data() for record in result]

        with self._driver.session() as session:
            try:
                return session.execute_read(_tx)
            except Neo4jError as exc:
                raise RuntimeError(f"Neo4j read query failed: {exc}") from exc
