**Запуск приложения**
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001 --no-access-log


5) Запустить ETL из Overpass
curl -X POST "http://localhost:8000/api/ingest/overpass" \
  -H "Content-Type: application/json" \
  -d '{"preset":"streets","source_name":"overpass_moscow","max_elements":500,"include_sample_if_empty":false}'

curl -X POST "http://localhost:8000/api/ingest/overpass" \
  -H "Content-Type: application/json" \
  -d '{"preset":"houses","source_name":"overpass_moscow","max_elements":200,"include_sample_if_empty":false}'

6) Neo4j Browser: http://localhost:7474

MATCH (s:Street) RETURN count(s) AS streets;
MATCH (a:Address) RETURN count(a) AS addresses;
MATCH (a:Address)-[:ON_STREET]->(s:Street)RETURN s.name, a.full_addressLIMIT 20;
Или через API:
curl -X POST "http://localhost:8000/api/query/cypher" -H "Content-Type: application/json" -d '{"query":"MATCH (s:Street) RETURN s.name AS name LIMIT 10"}'


7) curl -X POST "http://localhost:8000/api/ingest/overpass" \
  -H "Content-Type: application/json" \
  -d '{
    "preset": "both",
    "source_name": "overpass_moscow",
    "max_elements": 1000,
    "include_sample_if_empty": false
  }'

8) Асинхронный batch-job полной загрузки streets + houses
curl -sS -X POST "http://localhost:8000/api/ingest/overpass/job" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "both",
    "source_name": "overpass_moscow",
    "max_elements": 5000
  }'

Ответ содержит `job_id`. Проверка статуса:
curl -sS "http://localhost:8000/api/ingest/overpass/job/<job_id>"

Ниже рабочие примеры `curl` для запросов **через агента** (NL -> Cypher -> Neo4j) в ваш API.

### 1) Базовый NL-запрос через агента
```bash
curl -sS -X POST "http://localhost:8000/api/query/nl" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Сколько улиц в базе данных?"
  }'
```

{"question":"Сколько улиц в базе данных?","cypher":"MATCH (s:Street) RETURN count(s) AS streetCount LIMIT 1","rows":[{"streetCount":1338}],"row_count":1,"explanation":"Подсчитывает общее количество узлов с меткой Street в графе."}



### 2) Поиск районов
```bash
curl -sS -X POST "http://localhost:8000/api/query/nl" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Покажи 10 районов Москвы по алфавиту"
  }'
```

### 3) Адреса рядом с метро
```bash
curl -sS -X POST "http://localhost:8000/api/query/nl" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Покажи 5 адресов рядом с метро"
  }'
```

### 4) С красивым выводом через `jq`
```bash
curl -sS -X POST "http://localhost:8000/api/query/nl" \
  -H "Content-Type: application/json" \
  -d '{"question":"Сколько связей в графе и какие типы имеются?"}' 
```
curl -sS -X POST "http://localhost:8000/api/query/nl" \
  -H "Content-Type: application/json" \
  -d '{"question":"Какое количество всех связей в графе?"}' 

---

Если нужен контроль, что именно уходит в БД, смотри поле `cypher` в ответе — это запрос, который агент сгенерировал и который затем выполнился в Neo4j.

Для сравнения, **без агента** (прямой Cypher endpoint):
```bash
curl -sS -X POST "http://localhost:8000/api/query/cypher" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (m:MetroStation) RETURN m.name AS name ORDER BY name LIMIT 5",
    "params": {}
  }' | jq
```

curl -sS -X POST "http://localhost:8000/api/query/cypher" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (s:Street) RETURN count(s) AS streetCount LIMIT 1",
    "params": {}
  }' | jq


  ================================
  Загрузка всех данных через ETL:

curl -sS -X POST "http://localhost:8000/api/ingest/overpass/job" \
-H "Content-Type: application/json" \
-d '{
  "mode": "houses",
  "source_name": "overpass_moscow",
  "max_elements": null
}'

  ================================