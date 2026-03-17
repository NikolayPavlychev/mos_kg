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
5. Start Streamlit UI (optional):
   - `streamlit run streamlit_app.py`

## Tests

- `pytest -q`

## API

- `GET /api/health`
- `POST /api/ingest/run`
- `POST /api/ingest/overpass`
- `POST /api/ingest/overpass/job`
- `GET /api/ingest/overpass/job/{job_id}`
- `POST /api/query/cypher`
- `POST /api/query/nl`

## Streamlit UI

- File: `streamlit_app.py`
- Launch: `streamlit run streamlit_app.py`
- Supports:
  - Cypher requests to `POST /api/query/cypher` with optional JSON params
  - Natural language requests to `POST /api/query/nl`

## Notes

- `POST /api/ingest/run` supports two modes:
  - `source_kind=generic`: ingests JSON/CSV from `source_url` or `source_path`;
  - `source_kind=overpass`: fetches streets/houses for Moscow from Overpass API.
- Overpass ingestion uses retries with backoff; timeout/network failures are returned as `HTTP 504`.
- Overpass `houses` mode is fetched in bbox tiles across Moscow to reduce timeout risk.
- `POST /api/query/cypher` runs in read-only guarded mode (dangerous Cypher keywords are blocked).
- `POST /api/query/nl` supports `OPENAI` and `DeepSeek` providers via `LLM_PROVIDER`; if provider request fails, endpoint degrades to rule-based fallback.

## DeepSeek Setup for NL->Cypher

Set these variables in `.env`:

- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_API_KEY=<your-key>`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-chat`

Optional OpenAI mode (default):

- `LLM_PROVIDER=openai`
- `OPENAI_API_KEY=<your-key>`
- `OPENAI_MODEL=gpt-4o-mini`

### NL query example

```json
{
  "question": "покажи станции метро в графе"
}
```

Send to `POST /api/query/nl`. Response is plain text (`text/plain`) with only a detailed natural-language answer.

### Generic ingest request example

```json
{
  "source_kind": "generic",
  "source_url": "https://example.com/moscow_orgs.json",
  "source_format": "json",
  "source_name": "open_data_moscow",
  "include_sample_if_empty": true
}
```

### Overpass ingest request example

```json
{
  "source_kind": "overpass",
  "source_name": "overpass_moscow",
  "overpass_mode": "both",
  "overpass_max_elements": 5000,
  "include_sample_if_empty": true
}
```

### Overpass preset endpoint example

```json
{
  "preset": "streets",
  "source_name": "overpass_moscow",
  "max_elements": 5000,
  "include_sample_if_empty": true
}
```

### Async Overpass batch-job example

Start job:

```bash
curl -sS -X POST "http://localhost:8000/api/ingest/overpass/job" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "both",
    "source_name": "overpass_moscow",
    "max_elements": 1000
  }'
```

Check status by `job_id`:

```bash
curl -sS "http://localhost:8000/api/ingest/overpass/job/<job_id>"
```

The async job status transitions: `queued -> running -> succeeded/failed`.


curl -sS "http://localhost:8000/api/ingest/overpass/job/01676cf2-ef97-489d-91a5-669d32bafbf8"

Число всех улиц и домов в БД

curl -sS "https://overpass.kumi.systems/api/interpreter" \
  --data-urlencode 'data=
[out:json][timeout:180];
area["name"="Москва"]["boundary"="administrative"]->.a;
way["highway"]["name"](area.a);
out count;'


{
  "version": 0.6,
  "generator": "Overpass API 0.7.61.8 b1080abd",
  "osm3s": {
    "timestamp_osm_base": "2026-02-15T14:44:30Z",
    "timestamp_areas_base": "2026-02-15T14:44:30Z",
    "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
  },
  "elements": [

{
  "type": "count",
  "id": 0,
  "tags": {
    "nodes": "0",
    "ways": "43896",
    "relations": "0",
    "areas": "0",
    "total": "43896"
  }
}

  ]
}


curl -sS "https://overpass.kumi.systems/api/interpreter" \
  --data-urlencode 'data=
[out:json][timeout:180];
nwr["addr:housenumber"](55.48,37.30,55.65,37.52);
out count;'

{
  "version": 0.6,
  "generator": "Overpass API 0.7.61.8 b1080abd",
  "osm3s": {
    "timestamp_osm_base": "2026-03-16T23:50:53Z",
    "copyright": "The data included in this document is from www.openstreetmap.org. The data is made available under ODbL."
  },
  "elements": [

{
  "type": "count",
  "id": 0,
  "tags": {
    "nodes": "856",
    "ways": "20612",
    "relations": "921",
    "total": "22389"
  }
}

  ]
}

curl -sS "https://overpass.kumi.systems/api/interpreter" \
  --data-urlencode 'data=[out:json][timeout:180];nwr["addr:housenumber"](55.48,37.30,55.65,37.52);out count;'


for bbox in \
  "55.48,37.30,55.65,37.52" \
  "55.48,37.52,55.65,37.90" \
  "55.65,37.30,55.85,37.52" \
  "55.65,37.52,55.85,37.90"
do
  resp="$(curl -sS "https://overpass.kumi.systems/api/interpreter" \
    --data-urlencode "data=[out:json][timeout:180];nwr[\"addr:housenumber\"](${bbox});out count;")"

  echo "$resp" | jq -er '(.elements[0].tags.total // .elements[0].total) | tonumber' \
    || { echo "Ошибка ответа для bbox=$bbox"; echo "$resp"; echo 0; }
done | awk '{s+=$1} END {print s}'

jq: parse error: Invalid numeric literal at line 1, column 6
116300