import json

from app.core.config import get_settings

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class AgentService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None
        if self._settings.openai_api_key and OpenAI is not None:
            self._client = OpenAI(api_key=self._settings.openai_api_key)

    def question_to_cypher(self, question: str, max_rows: int) -> tuple[str, str]:
        if self._client is not None:
            generated = self._question_to_cypher_llm(question=question, max_rows=max_rows)
            if generated is not None:
                return generated
        return self._question_to_cypher_fallback(question=question, max_rows=max_rows)

    def _question_to_cypher_llm(self, question: str, max_rows: int) -> tuple[str, str] | None:
        prompt = f"""
You are a Cypher generator for a Moscow city knowledge graph in Neo4j.

Graph ontology (main labels):
- City
- District
- Street
- Address
- Place
- Organization
- Category
- HistoricalEvent
- Landmark
- TransportStop
- MetroStation

Known relations (examples):
- (d:District)-[:PART_OF]->(c:City)
- (s:Street)-[:IN_DISTRICT]->(d:District)
- (a:Address)-[:ON_STREET]->(s:Street)
- (p:Place)-[:LOCATED_AT]->(a:Address)
- (o:Organization)-[:OPERATES_AT]->(p:Place)
- (p:Place)-[:HAS_CATEGORY]->(cat:Category)
- (m:MetroStation)-[:NEAR]->(p:Place)

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
        try:
            response = self._client.responses.create(
                model=self._settings.openai_model,
                input=prompt,
            )
            text = response.output_text.strip()
            payload = json.loads(text)
            cypher = payload["cypher"].strip()
            explanation = payload.get("explanation", "Сформирован запрос по вопросу пользователя.")
            return cypher, explanation
        except Exception:
            return None

    def _question_to_cypher_fallback(self, question: str, max_rows: int) -> tuple[str, str]:
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
