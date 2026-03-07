from fastapi.testclient import TestClient

from app.main import app


def test_root() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "env" in payload


def test_health(monkeypatch) -> None:
    from app.db import neo4j_client

    def _fake_run_read(self, query: str, params=None, timeout_s: int = 3):
        return [{"status": "ok"}]

    monkeypatch.setattr(neo4j_client.Neo4jClient, "run_read", _fake_run_read)
    monkeypatch.setattr(neo4j_client.Neo4jClient, "close", lambda self: None)

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"api": "ok", "db": "ok"}


def test_query_cypher(monkeypatch) -> None:
    from app.services import query_service

    monkeypatch.setattr(query_service.QueryService, "__init__", lambda self: None)
    monkeypatch.setattr(query_service.QueryService, "close", lambda self: None)
    monkeypatch.setattr(
        query_service.QueryService,
        "run_cypher",
        lambda self, query, params=None: [{"name": "Тверской"}],
    )

    client = TestClient(app)
    response = client.post("/api/query/cypher", json={"query": "MATCH (d:District) RETURN d"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["name"] == "Тверской"


def test_query_nl(monkeypatch) -> None:
    from app.services import agent_service, query_service

    monkeypatch.setattr(
        agent_service.AgentService,
        "question_to_cypher",
        lambda self, question, max_rows: (
            "MATCH (m:MetroStation) RETURN m.name AS name LIMIT 10",
            "Тестовый ответ агента",
        ),
    )
    monkeypatch.setattr(query_service.QueryService, "__init__", lambda self: None)
    monkeypatch.setattr(query_service.QueryService, "close", lambda self: None)
    monkeypatch.setattr(
        query_service.QueryService,
        "run_cypher",
        lambda self, query, params=None: [{"name": "Арбатская"}],
    )

    client = TestClient(app)
    response = client.post("/api/query/nl", json={"question": "покажи метро"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["cypher"].startswith("MATCH (m:MetroStation)")


def test_ingest_run_real_source(monkeypatch) -> None:
    from app.api.routes import ingest

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_real_ingest",
        lambda source_format, source_name, source_url=None, source_path=None: 5,
    )
    monkeypatch.setattr(ingest, "run_sample_ingest", lambda: None)

    client = TestClient(app)
    response = client.post(
        "/api/ingest/run",
        json={
            "source_url": "https://example.com/data.json",
            "source_format": "json",
            "source_name": "test_source",
            "include_sample_if_empty": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded_rows"] == 5
    assert payload["status"] == "ok"


def test_ingest_run_fallback_to_sample(monkeypatch) -> None:
    from app.api.routes import ingest

    state = {"sample_called": False}

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_real_ingest",
        lambda source_format, source_name, source_url=None, source_path=None: 0,
    )
    monkeypatch.setattr(ingest, "run_sample_ingest", lambda: state.update({"sample_called": True}))

    client = TestClient(app)
    response = client.post(
        "/api/ingest/run",
        json={
            "source_format": "json",
            "source_name": "test_source",
            "include_sample_if_empty": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded_rows"] == 0
    assert state["sample_called"] is True
