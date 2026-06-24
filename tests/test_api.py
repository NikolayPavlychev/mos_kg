from fastapi.testclient import TestClient
from types import SimpleNamespace

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
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "Тестовый ответ агента" not in body
    assert "name: Арбатская" in body


def test_query_nl_deepseek_success(monkeypatch) -> None:
    from app.api.routes import query as query_route
    from app.services import agent_service, query_service

    fake_agent_settings = SimpleNamespace(
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )
    fake_route_settings = SimpleNamespace(app_cypher_max_rows=10)

    class _FakeCompletions:
        def create(self, model, messages):
            assert model == "deepseek-chat"
            assert messages and messages[0]["role"] == "user"
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"cypher":"MATCH (d:District) RETURN d.name AS name LIMIT 10","explanation":"Запрос по районам."}'
                        )
                    )
                ]
            )

    class _FakeOpenAI:
        def __init__(self, api_key, base_url=None):
            assert api_key == "test-key"
            assert base_url == "https://api.deepseek.com"
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr(agent_service, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(agent_service, "get_settings", lambda: fake_agent_settings)
    monkeypatch.setattr(query_route, "get_settings", lambda: fake_route_settings)

    monkeypatch.setattr(query_service.QueryService, "__init__", lambda self: None)
    monkeypatch.setattr(query_service.QueryService, "close", lambda self: None)
    monkeypatch.setattr(
        query_service.QueryService,
        "run_cypher",
        lambda self, query, params=None: [{"name": "Тверской"}],
    )

    client = TestClient(app)
    response = client.post("/api/query/nl", json={"question": "покажи районы"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "Запрос по районам." not in body
    assert "name: Тверской" in body


def test_query_nl_deepseek_provider_error_uses_fallback(monkeypatch) -> None:
    from app.api.routes import query as query_route
    from app.services import agent_service, query_service

    fake_agent_settings = SimpleNamespace(
        llm_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
        openai_api_key=None,
        openai_model="gpt-4o-mini",
    )
    fake_route_settings = SimpleNamespace(app_cypher_max_rows=7)

    class _FakeCompletions:
        def create(self, model, messages):
            raise RuntimeError("provider unavailable")

    class _FakeOpenAI:
        def __init__(self, api_key, base_url=None):
            self.chat = SimpleNamespace(completions=_FakeCompletions())

    state = {"query": None}

    monkeypatch.setattr(agent_service, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(agent_service, "get_settings", lambda: fake_agent_settings)
    monkeypatch.setattr(query_route, "get_settings", lambda: fake_route_settings)

    monkeypatch.setattr(query_service.QueryService, "__init__", lambda self: None)
    monkeypatch.setattr(query_service.QueryService, "close", lambda self: None)

    def _fake_run_cypher(self, query, params=None):
        state["query"] = query
        return [{"name": "Арбат"}]

    monkeypatch.setattr(query_service.QueryService, "run_cypher", _fake_run_cypher)

    client = TestClient(app)
    response = client.post("/api/query/nl", json={"question": "покажи район"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "LLM-провайдер временно недоступен" not in body
    assert state["query"] == "MATCH (d:District) RETURN d.name AS name ORDER BY name LIMIT 7"
    assert "name: Арбат" in body


def test_build_nl_answer_formats_fields_and_limits_preview() -> None:
    from app.api.routes.query import _build_nl_answer

    rows = [
        {"station_name": "Арбатская", "line": "Арбатско-Покровская", "note": None},
        {"station_name": "Смоленская", "line": "Арбатско-Покровская"},
        {"station_name": "Киевская", "line": "Кольцевая"},
        {"station_name": "Охотный Ряд", "line": "Сокольническая"},
        {"station_name": "Тверская", "line": "Замоскворецкая"},
        {"station_name": "Пушкинская", "line": "Таганско-Краснопресненская"},
    ]

    answer = _build_nl_answer("Нашел станции метро.", rows)

    assert "Найдено записей: 6." in answer
    assert "1) station name: Арбатская; line: Арбатско-Покровская; note: нет данных" in answer
    assert "и еще 1 записей." in answer
    assert "Нашел станции метро." not in answer


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
            "source_kind": "generic",
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
            "source_kind": "generic",
            "source_format": "json",
            "source_name": "test_source",
            "include_sample_if_empty": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded_rows"] == 0
    assert state["sample_called"] is True


def test_ingest_run_overpass(monkeypatch) -> None:
    from app.api.routes import ingest

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_overpass_ingest",
        lambda source_name, mode="both", max_elements=5000: 12,
    )
    monkeypatch.setattr(ingest, "run_sample_ingest", lambda: None)

    client = TestClient(app)
    response = client.post(
        "/api/ingest/run",
        json={
            "source_kind": "overpass",
            "source_name": "overpass_moscow",
            "overpass_mode": "both",
            "overpass_max_elements": 1200,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded_rows"] == 12
    assert payload["status"] == "ok"


def test_ingest_run_overpass_full_mode_uses_null_max_elements(monkeypatch) -> None:
    from app.api.routes import ingest

    captured: dict[str, object] = {}

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)

    def _fake_run_overpass_ingest(source_name, mode="both", max_elements=5000):
        captured["source_name"] = source_name
        captured["mode"] = mode
        captured["max_elements"] = max_elements
        return 77

    monkeypatch.setattr(ingest, "run_overpass_ingest", _fake_run_overpass_ingest)
    monkeypatch.setattr(ingest, "run_sample_ingest", lambda: None)

    client = TestClient(app)
    response = client.post(
        "/api/ingest/run",
        json={
            "source_kind": "overpass",
            "source_name": "overpass_moscow",
            "overpass_mode": "houses",
            "overpass_max_elements": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["loaded_rows"] == 77
    assert captured["max_elements"] is None


def test_ingest_overpass_endpoint_with_preset(monkeypatch) -> None:
    from app.api.routes import ingest

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_overpass_ingest",
        lambda source_name, mode="both", max_elements=5000: 20 if mode == "streets" else 0,
    )
    monkeypatch.setattr(ingest, "run_sample_ingest", lambda: None)

    client = TestClient(app)
    response = client.post(
        "/api/ingest/overpass",
        json={
            "preset": "streets",
            "source_name": "overpass_moscow",
            "max_elements": 1500,
            "include_sample_if_empty": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["loaded_rows"] == 20
    assert payload["status"] == "ok"


def test_ingest_overpass_endpoint_invalid_preset() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/ingest/overpass",
        json={
            "preset": "invalid",
            "source_name": "overpass_moscow",
            "max_elements": 1500,
        },
    )
    assert response.status_code == 400


def test_ingest_overpass_endpoint_returns_504_on_overpass_timeout(monkeypatch) -> None:
    from app.api.routes import ingest
    from scripts.etl.overpass_ingest import OverpassFetchError

    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_overpass_ingest",
        lambda source_name, mode="both", max_elements=5000: (_ for _ in ()).throw(
            OverpassFetchError("Overpass API request timed out after retries.")
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/api/ingest/overpass",
        json={
            "preset": "both",
            "source_name": "overpass_moscow",
            "max_elements": 1000,
            "include_sample_if_empty": False,
        },
    )
    assert response.status_code == 504


def test_ingest_overpass_job_success(monkeypatch) -> None:
    from app.api.routes import ingest
    from app.services.ingest_job_service import IngestJobService

    monkeypatch.setattr(ingest, "job_service", IngestJobService())
    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)

    def _fake_run_overpass_ingest(
        source_name, mode="both", max_elements=5000, progress_callback=None
    ):
        if progress_callback is not None:
            progress_callback("fetch", "Fetched data for job.", 1)
            progress_callback("transform", "Transformed data for job.", 2)
            progress_callback("load", "Loaded data for job.", 3)
        return 42

    monkeypatch.setattr(ingest, "run_overpass_ingest", _fake_run_overpass_ingest)
    monkeypatch.setattr(
        ingest,
        "_spawn_job_worker",
        lambda job_id: ingest._run_overpass_ingest_job(job_id),
    )

    client = TestClient(app)
    start_response = client.post(
        "/api/ingest/overpass/job",
        json={"mode": "both", "source_name": "overpass_moscow", "max_elements": 1200},
    )
    assert start_response.status_code == 202
    start_payload = start_response.json()
    assert "job_id" in start_payload

    status_response = client.get(f"/api/ingest/overpass/job/{start_payload['job_id']}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "succeeded"
    assert status_payload["loaded_rows"] == 42
    assert status_payload["error"] is None
    assert status_payload["progress"]["stage"] == "done"
    assert status_payload["started_at"] is not None
    assert status_payload["finished_at"] is not None


def test_ingest_overpass_job_failed_status(monkeypatch) -> None:
    from app.api.routes import ingest
    from app.services.ingest_job_service import IngestJobService
    from scripts.etl.overpass_ingest import OverpassFetchError

    monkeypatch.setattr(ingest, "job_service", IngestJobService())
    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)
    monkeypatch.setattr(
        ingest,
        "run_overpass_ingest",
        lambda source_name, mode="both", max_elements=5000, progress_callback=None: (_ for _ in ()).throw(
            OverpassFetchError("Overpass mirror timeout")
        ),
    )
    monkeypatch.setattr(
        ingest,
        "_spawn_job_worker",
        lambda job_id: ingest._run_overpass_ingest_job(job_id),
    )

    client = TestClient(app)
    start_response = client.post(
        "/api/ingest/overpass/job",
        json={"mode": "both", "source_name": "overpass_moscow", "max_elements": 1200},
    )
    assert start_response.status_code == 202
    job_id = start_response.json()["job_id"]

    status_response = client.get(f"/api/ingest/overpass/job/{job_id}")
    assert status_response.status_code == 200
    payload = status_response.json()
    assert payload["status"] == "failed"
    assert "Overpass mirror timeout" in payload["error"]
    assert payload["finished_at"] is not None


def test_ingest_overpass_job_supports_null_max_elements(monkeypatch) -> None:
    from app.api.routes import ingest
    from app.services.ingest_job_service import IngestJobService

    captured: dict[str, object] = {}

    monkeypatch.setattr(ingest, "job_service", IngestJobService())
    monkeypatch.setattr(ingest, "run_schema_bootstrap", lambda: None)

    def _fake_run_overpass_ingest(
        source_name, mode="both", max_elements=5000, progress_callback=None
    ):
        captured["max_elements"] = max_elements
        if progress_callback is not None:
            progress_callback("fetch", "Fetched data for job.", 1)
            progress_callback("transform", "Transformed data for job.", 2)
            progress_callback("load", "Loaded data for job.", 3)
        return 12

    monkeypatch.setattr(ingest, "run_overpass_ingest", _fake_run_overpass_ingest)
    monkeypatch.setattr(
        ingest,
        "_spawn_job_worker",
        lambda job_id: ingest._run_overpass_ingest_job(job_id),
    )

    client = TestClient(app)
    response = client.post(
        "/api/ingest/overpass/job",
        json={"mode": "houses", "source_name": "overpass_moscow", "max_elements": None},
    )
    assert response.status_code == 202
    assert captured["max_elements"] is None
