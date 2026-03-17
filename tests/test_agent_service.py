from types import SimpleNamespace

from app.services import agent_service


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider="openai",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
        deepseek_api_key=None,
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        app_cypher_timeout_seconds=10,
        app_schema_cache_ttl_seconds=120,
    )


def test_load_graph_schema_context_from_db(monkeypatch) -> None:
    class _FakeNeo4jClient:
        def run_read(self, query: str, params=None, timeout_s: int = 10):
            if "CALL db.labels()" in query:
                return [{"label": "City"}, {"label": "District"}]
            return [
                {
                    "from_labels": ["District"],
                    "rel_type": "PART_OF",
                    "to_labels": ["City"],
                }
            ]

        def close(self) -> None:
            return None

    monkeypatch.setattr(agent_service, "get_settings", _fake_settings)
    monkeypatch.setattr(agent_service, "Neo4jClient", _FakeNeo4jClient)
    agent_service.AgentService._reset_schema_cache_for_tests()

    service = agent_service.AgentService()
    labels, relations = service._load_graph_schema_context()

    assert labels == ["City", "District"]
    assert relations == ["(a:District)-[:PART_OF]->(b:City)"]


def test_load_graph_schema_context_fallback_on_db_error(monkeypatch) -> None:
    class _FailingNeo4jClient:
        def run_read(self, query: str, params=None, timeout_s: int = 10):
            raise RuntimeError("db unavailable")

        def close(self) -> None:
            return None

    monkeypatch.setattr(agent_service, "get_settings", _fake_settings)
    monkeypatch.setattr(agent_service, "Neo4jClient", _FailingNeo4jClient)
    agent_service.AgentService._reset_schema_cache_for_tests()

    service = agent_service.AgentService()
    labels, relations = service._load_graph_schema_context()

    assert labels == agent_service.DEFAULT_GRAPH_LABELS
    assert relations == agent_service.DEFAULT_GRAPH_RELATIONS


def test_load_graph_schema_context_uses_cache_across_instances(monkeypatch) -> None:
    calls = {"count": 0}

    class _CountingNeo4jClient:
        def run_read(self, query: str, params=None, timeout_s: int = 10):
            calls["count"] += 1
            if "CALL db.labels()" in query:
                return [{"label": "City"}]
            return [{"from_labels": ["District"], "rel_type": "PART_OF", "to_labels": ["City"]}]

        def close(self) -> None:
            return None

    monkeypatch.setattr(agent_service, "get_settings", _fake_settings)
    monkeypatch.setattr(agent_service, "Neo4jClient", _CountingNeo4jClient)
    agent_service.AgentService._reset_schema_cache_for_tests()

    service1 = agent_service.AgentService()
    service2 = agent_service.AgentService()

    service1._load_graph_schema_context()
    service2._load_graph_schema_context()

    # First load performs two DB reads (labels + relations), second is served from cache.
    assert calls["count"] == 2

