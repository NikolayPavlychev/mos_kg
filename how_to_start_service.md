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