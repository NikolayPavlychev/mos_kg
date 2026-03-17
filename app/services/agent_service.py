import json
import re
import threading
import time

from app.core.config import get_settings
from app.db.neo4j_client import Neo4jClient

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class LLMProviderError(RuntimeError):
    pass


DEFAULT_GRAPH_LABELS = [
    "City",
    "District",
    "Street",
    "Address",
    "Place",
    "Organization",
    "Category",
    "HistoricalEvent",
    "Landmark",
    "TransportStop",
    "MetroStation",
]

DEFAULT_GRAPH_RELATIONS = [
    "(d:District)-[:PART_OF]->(c:City)",
    "(s:Street)-[:IN_DISTRICT]->(d:District)",
    "(a:Address)-[:ON_STREET]->(s:Street)",
    "(p:Place)-[:LOCATED_AT]->(a:Address)",
    "(o:Organization)-[:OPERATES_AT]->(p:Place)",
    "(p:Place)-[:HAS_CATEGORY]->(cat:Category)",
    "(m:MetroStation)-[:NEAR]->(p:Place)",
]


class AgentService:
    _schema_cache_lock = threading.Lock()
    _schema_cache_expires_at: float = 0.0
    _schema_cache_value: tuple[list[str], list[str]] | None = None

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        self._provider = (self._settings.llm_provider or "openai").strip().lower()

        if OpenAI is None:
            return

        if self._provider == "openai" and self._settings.openai_api_key:
            self._client = OpenAI(api_key=self._settings.openai_api_key)
        elif self._provider == "deepseek" and self._settings.deepseek_api_key:
            self._client = OpenAI(
                api_key=self._settings.deepseek_api_key,
                base_url=self._settings.deepseek_base_url,
            )

    def question_to_cypher(self, question: str, max_rows: int) -> tuple[str, str]:
        if self._client is None:
            return self._question_to_cypher_fallback(question=question, max_rows=max_rows)

        try:
            if self._provider == "deepseek":
                return self._question_to_cypher_deepseek(
                    question=question, max_rows=max_rows
                )
            return self._question_to_cypher_openai(question=question, max_rows=max_rows)
        except LLMProviderError:
            cypher, explanation = self._question_to_cypher_fallback(
                question=question, max_rows=max_rows
            )
            return (
                cypher,
                f"{explanation} LLM-провайдер временно недоступен, использован fallback.",
            )

    def _question_to_cypher_openai(
        self, question: str, max_rows: int
    ) -> tuple[str, str]:
        return self._question_to_cypher_via_provider(
            question=question,
            max_rows=max_rows,
            model=self._settings.openai_model,
            provider_name="openai",
        )

    def _question_to_cypher_deepseek(
        self, question: str, max_rows: int
    ) -> tuple[str, str]:
        return self._question_to_cypher_via_provider(
            question=question,
            max_rows=max_rows,
            model=self._settings.deepseek_model,
            provider_name="deepseek",
        )

    def _question_to_cypher_via_provider(
        self, question: str, max_rows: int, model: str, provider_name: str
    ) -> tuple[str, str]:
        if self._client is None:
            raise LLMProviderError(f"{provider_name} client is not configured.")

        prompt = self._build_prompt(question=question, max_rows=max_rows)
        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise LLMProviderError(f"{provider_name} returned empty content.")
            payload = self._parse_llm_payload(text)
            cypher = payload["cypher"].strip()
            explanation = payload.get(
                "explanation", "Сформирован запрос по вопросу пользователя."
            )
            return cypher, explanation
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError(f"{provider_name} request failed.") from exc

    def _build_prompt(self, question: str, max_rows: int) -> str:
        labels, relations = self._load_graph_schema_context()
        labels_block = "\n".join(f"- {label}" for label in labels)
        relations_block = "\n".join(f"- {relation}" for relation in relations)

        return f"""
You are a Cypher generator for a Moscow city knowledge graph in Neo4j.

Graph ontology (main labels):
{labels_block}

Known relations (examples):
{relations_block}

Rules:
1) Generate read-only Cypher only. Never use CREATE/MERGE/SET/DELETE/REMOVE/DROP.
2) Always include LIMIT <= {max_rows}.
3) Return only valid Cypher for Neo4j 5.
4) If user intent is vague, return a summary query over labels.

Return strict JSON:
{{
  "cypher": "<query>",
  "explanation": "<short russian explanation>"
}}

User question:
{question}
"""

    def _load_graph_schema_context(self) -> tuple[list[str], list[str]]:
        cls = type(self)
        ttl_s = max(0, int(getattr(self._settings, "app_schema_cache_ttl_seconds", 120)))
        if ttl_s > 0:
            now = time.monotonic()
            with cls._schema_cache_lock:
                if (
                    cls._schema_cache_value is not None
                    and now < cls._schema_cache_expires_at
                ):
                    return cls._schema_cache_value

        loaded = self._fetch_graph_schema_context()

        if ttl_s > 0:
            now = time.monotonic()
            with cls._schema_cache_lock:
                if (
                    cls._schema_cache_value is not None
                    and now < cls._schema_cache_expires_at
                ):
                    return cls._schema_cache_value
                cls._schema_cache_value = loaded
                cls._schema_cache_expires_at = now + ttl_s

        return loaded

    def _fetch_graph_schema_context(self) -> tuple[list[str], list[str]]:
        client = Neo4jClient()
        try:
            timeout_s = min(self._settings.app_cypher_timeout_seconds, 5)
            labels_rows = client.run_read(
                "CALL db.labels() YIELD label RETURN label ORDER BY label",
                timeout_s=timeout_s,
            )
            relation_rows = client.run_read(
                "MATCH (a)-[r]->(b) "
                "RETURN DISTINCT labels(a) AS from_labels, type(r) AS rel_type, labels(b) AS to_labels "
                "ORDER BY rel_type LIMIT 25",
                timeout_s=timeout_s,
            )

            labels = [
                str(row.get("label", "")).strip()
                for row in labels_rows
                if str(row.get("label", "")).strip()
            ]
            relations = self._format_relation_examples(relation_rows)

            if not labels:
                labels = DEFAULT_GRAPH_LABELS
            if not relations:
                relations = DEFAULT_GRAPH_RELATIONS
            return labels, relations
        except Exception:
            return DEFAULT_GRAPH_LABELS, DEFAULT_GRAPH_RELATIONS
        finally:
            client.close()

    def _format_relation_examples(self, rows: list[dict]) -> list[str]:
        formatted: list[str] = []
        for row in rows:
            rel_type = str(row.get("rel_type", "")).strip()
            if not rel_type:
                continue

            from_labels = row.get("from_labels") or []
            to_labels = row.get("to_labels") or []
            from_label = (
                str(from_labels[0]).strip()
                if isinstance(from_labels, list) and from_labels
                else "Node"
            )
            to_label = (
                str(to_labels[0]).strip()
                if isinstance(to_labels, list) and to_labels
                else "Node"
            )
            formatted.append(f"(a:{from_label})-[:{rel_type}]->(b:{to_label})")
        return formatted

    @classmethod
    def _reset_schema_cache_for_tests(cls) -> None:
        with cls._schema_cache_lock:
            cls._schema_cache_value = None
            cls._schema_cache_expires_at = 0.0

    def _parse_llm_payload(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
        if fenced_match:
            return json.loads(fenced_match.group(1))

        object_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if object_match:
            return json.loads(object_match.group(1))

        raise json.JSONDecodeError("No JSON object found in provider response.", text, 0)

    def _question_to_cypher_fallback(
        self, question: str, max_rows: int
    ) -> tuple[str, str]:
        q = question.lower()

        if "район" in q:
            return (
                f"MATCH (d:District) RETURN d.name AS name ORDER BY name LIMIT {max_rows}",
                "Возвращаю список районов из графа.",
            )
        if "метро" in q:
            return (
                f"MATCH (m:MetroStation) RETURN m.name AS name ORDER BY name LIMIT {max_rows}",
                "Возвращаю список станций метро.",
            )
        if "адрес" in q:
            return (
                f"MATCH (a:Address) RETURN a.full_address AS address ORDER BY address LIMIT {max_rows}",
                "Возвращаю список адресов.",
            )

        return (
            f"MATCH (n) WITH labels(n) AS labels, count(*) AS count RETURN labels, count ORDER BY count DESC LIMIT {max_rows}",
            "Показываю сводку по типам узлов как универсальный ответ для MVP.",
        )
