import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from neo4j import GraphDatabase

from app.core.config import get_settings


@dataclass
class NormalizedOrgRecord:
    organization_id: str
    organization_name: str
    category_name: str
    city_name: str
    district_name: str
    full_address: str
    lat: float | None
    lon: float | None
    source: str


def run_real_ingest(
    source_format: str,
    source_name: str,
    source_url: str | None = None,
    source_path: str | None = None,
) -> int:
    raw_rows = extract_rows(source_format=source_format, source_url=source_url, source_path=source_path)
    normalized = transform_rows(raw_rows=raw_rows, source_name=source_name)
    if not normalized:
        return 0
    load_rows_to_neo4j(normalized)
    return len(normalized)


def extract_rows(source_format: str, source_url: str | None, source_path: str | None) -> list[dict[str, Any]]:
    if source_url:
        raw_text = _read_text_from_url(source_url)
    elif source_path:
        raw_text = Path(source_path).read_text(encoding="utf-8")
    else:
        return []

    source_format = source_format.lower().strip()
    if source_format == "json":
        data = json.loads(raw_text)
        if isinstance(data, dict):
            for key in ("items", "results", "data"):
                maybe_items = data.get(key)
                if isinstance(maybe_items, list):
                    return [row for row in maybe_items if isinstance(row, dict)]
            return []
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    if source_format == "csv":
        reader = csv.DictReader(raw_text.splitlines())
        return [dict(row) for row in reader]

    raise ValueError("Unsupported source_format. Use json or csv.")


def transform_rows(raw_rows: list[dict[str, Any]], source_name: str) -> list[NormalizedOrgRecord]:
    out: list[NormalizedOrgRecord] = []
    for row in raw_rows:
        name = _pick_first(row, ["name", "organization_name", "org_name", "title"])
        if not name:
            continue

        district = _pick_first(row, ["district", "adm_area", "area", "rayon"]) or "Не указан"
        city = _pick_first(row, ["city"]) or "Москва"
        address = _pick_first(row, ["address", "full_address", "location"]) or "Не указан"
        category = _pick_first(row, ["category", "type", "rubric"]) or "Объект"
        rec_id = _pick_first(row, ["id", "global_id", "uid"]) or _stable_id(name, address, district)
        lat = _to_float(_pick_first(row, ["lat", "latitude", "geo_lat"]))
        lon = _to_float(_pick_first(row, ["lon", "longitude", "geo_lon"]))

        out.append(
            NormalizedOrgRecord(
                organization_id=str(rec_id),
                organization_name=name,
                category_name=category,
                city_name=city,
                district_name=district,
                full_address=address,
                lat=lat,
                lon=lon,
                source=source_name,
            )
        )

    return _dedupe(out)


def load_rows_to_neo4j(rows: list[NormalizedOrgRecord]) -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    with driver.session() as session:
        for row in rows:
            session.run(
                """
                MERGE (c:City {name: $city_name})
                MERGE (d:District {name: $district_name})
                MERGE (d)-[:PART_OF]->(c)

                MERGE (a:Address {full_address: $full_address})
                SET a.lat = $lat, a.lon = $lon, a.source = $source

                MERGE (cat:Category {name: $category_name})

                MERGE (o:Organization {id: $organization_id})
                SET o.name = $organization_name, o.source = $source

                MERGE (p:Place {id: 'place:' + $organization_id})
                SET p.name = $organization_name, p.source = $source

                MERGE (o)-[:OPERATES_AT]->(p)
                MERGE (p)-[:LOCATED_AT]->(a)
                MERGE (p)-[:HAS_CATEGORY]->(cat)
                MERGE (a)-[:IN_DISTRICT]->(d)
                """,
                {
                    "organization_id": row.organization_id,
                    "organization_name": row.organization_name,
                    "category_name": row.category_name,
                    "city_name": row.city_name,
                    "district_name": row.district_name,
                    "full_address": row.full_address,
                    "lat": row.lat,
                    "lon": row.lon,
                    "source": row.source,
                },
            )

    driver.close()


def _read_text_from_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "mos-kg-etl/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _pick_first(row: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        value_s = str(value).strip()
        if value_s:
            return value_s
    return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _stable_id(name: str, address: str, district: str) -> str:
    return f"{name.lower()}|{address.lower()}|{district.lower()}"


def _dedupe(rows: list[NormalizedOrgRecord]) -> list[NormalizedOrgRecord]:
    seen: set[str] = set()
    out: list[NormalizedOrgRecord] = []
    for row in rows:
        key = row.organization_id
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
