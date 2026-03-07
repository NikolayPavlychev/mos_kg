# Moscow Knowledge Graph

MVP implementation for a Moscow knowledge graph on Neo4j with FastAPI endpoints and an AI-assisted natural-language query route.

## Quick Start

1. Create env file:
   - `cp .env.example .env`
2. Start Neo4j:
   - `docker compose up -d`
3. Create and activate virtualenv, then install deps:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
4. Start API:
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`

## Tests

- `pytest -q`

## API

- `GET /api/health`
- `POST /api/ingest/run`
- `POST /api/query/cypher`
- `POST /api/query/nl`

## Notes

- `POST /api/ingest/run` creates baseline schema and ingests JSON/CSV from `source_url` or `source_path`; falls back to sample data when source is empty.
- `POST /api/query/cypher` runs in read-only guarded mode (dangerous Cypher keywords are blocked).
- `POST /api/query/nl` uses OpenAI (if `OPENAI_API_KEY` is set) and falls back to a rule-based translator when LLM is unavailable.

### Ingest request example

```json
{
  "source_url": "https://example.com/moscow_orgs.json",
  "source_format": "json",
  "source_name": "open_data_moscow",
  "include_sample_if_empty": true
}
```
