from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import get_settings
from neo4j import GraphDatabase

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 2
# south, west, north, east (rough split of Moscow bbox into tiles)
MOSCOW_HOUSE_BBOX_TILES = [
    (55.48, 37.30, 55.65, 37.52),
    (55.48, 37.52, 55.65, 37.90),
    (55.65, 37.30, 55.85, 37.52),
    (55.65, 37.52, 55.85, 37.90),
]


class OverpassFetchError(RuntimeError):
    """Raised when Overpass endpoint is unavailable or timed out."""


ProgressCallback = Callable[[str, str, int], None]


@dataclass
class StreetRecord:
    osm_id: str
    name: str
    lat: float | None
    lon: float | None
    source: str


@dataclass
class HouseRecord:
    osm_id: str
    house_number: str
    street_name: str | None
    full_address: str
    lat: float | None
    lon: float | None
    source: str


def run_overpass_ingest(
    source_name: str,
    mode: str = "both",
    max_elements: int = 5000,
    progress_callback: ProgressCallback | None = None,
) -> int:
    mode_norm = mode.lower().strip()
    if mode_norm not in {"streets", "houses", "both"}:
        raise ValueError("overpass_mode must be one of: streets, houses, both")

    _emit_progress(progress_callback, "fetch", "Fetching Overpass elements.", 1)
    overpass_data = _fetch_overpass_elements(
        mode=mode_norm,
        max_elements=max_elements,
        progress_callback=progress_callback,
    )
    _emit_progress(progress_callback, "transform", "Transforming Overpass elements.", 2)
    streets, houses = _transform_elements(overpass_data, source_name=source_name)
    _emit_progress(progress_callback, "load", "Loading transformed rows to Neo4j.", 3)
    _load_to_neo4j(streets=streets, houses=houses)
    _emit_progress(progress_callback, "load", "Neo4j load completed.", 4)
    return len(streets) + len(houses)


def _fetch_overpass_elements(
    mode: str,
    max_elements: int,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    elements: list[dict] = []

    if mode in {"streets", "both"}:
        streets_query = f"""
        [out:json][timeout:90];
        area["name"="Москва"]["boundary"="administrative"]->.searchArea;
        (
          way["highway"]["name"](area.searchArea);
        );
        out tags center {max_elements};
        """
        streets_data = _fetch_query_with_retry(streets_query)
        street_elements = streets_data.get("elements", [])
        if isinstance(street_elements, list):
            elements.extend(street_elements)

    if mode in {"houses", "both"}:
        per_tile_limit = max(100, int(max_elements / len(MOSCOW_HOUSE_BBOX_TILES)))
        house_elements: list[dict] = []
        failed_tiles = 0

        for idx, (south, west, north, east) in enumerate(MOSCOW_HOUSE_BBOX_TILES, start=1):
            bbox = f"{south},{west},{north},{east}"
            houses_query = f"""
            [out:json][timeout:60];
            (
              nwr["addr:housenumber"]({bbox});
            );
            out tags center {per_tile_limit};
            """
            try:
                houses_data = _fetch_query_with_retry(houses_query)
                tile_elements = houses_data.get("elements", [])
                if isinstance(tile_elements, list):
                    house_elements.extend(tile_elements)
                _emit_progress(
                    progress_callback,
                    "fetch",
                    f"Houses tile {idx}/{len(MOSCOW_HOUSE_BBOX_TILES)} fetched.",
                    1,
                )
            except OverpassFetchError:
                failed_tiles += 1
                _emit_progress(
                    progress_callback,
                    "fetch",
                    f"Houses tile {idx}/{len(MOSCOW_HOUSE_BBOX_TILES)} failed; continuing.",
                    1,
                )
                continue

        if failed_tiles == len(MOSCOW_HOUSE_BBOX_TILES):
            raise OverpassFetchError(
                "Overpass houses ingestion failed for all Moscow tiles due to timeout/network errors."
            )

        elements.extend(house_elements[:max_elements])

    return {"elements": elements}


def _fetch_query_with_retry(query: str) -> dict:
    settings = get_settings()
    last_error: Exception | None = None

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return _post_overpass_query(settings.app_overpass_api_url, query)
        except (TimeoutError, URLError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == RETRY_ATTEMPTS:
                break
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise OverpassFetchError(
        "Overpass API request timed out or failed after retries. "
        "Try smaller max_elements, preset=streets/houses, or another Overpass mirror."
    ) from last_error


def _post_overpass_query(url: str, query: str) -> dict:
    payload = urlencode({"data": query}).encode("utf-8")
    request = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "User-Agent": "mos-kg-overpass/0.1",
        },
    )
    with urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _emit_progress(
    progress_callback: ProgressCallback | None, stage: str, message: str, completed_steps: int
) -> None:
    if progress_callback is None:
        return
    progress_callback(stage, message, completed_steps)


def _transform_elements(
    data: dict, source_name: str
) -> tuple[list[StreetRecord], list[HouseRecord]]:
    elements = data.get("elements", [])
    streets: list[StreetRecord] = []
    houses: list[HouseRecord] = []

    seen_streets: set[str] = set()
    seen_houses: set[str] = set()

    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            continue

        element_type = str(element.get("type", ""))
        raw_id = element.get("id")
        if raw_id is None:
            continue
        osm_id = f"{element_type}/{raw_id}"

        lat, lon = _coords_from_element(element)

        highway = tags.get("highway")
        street_name = _clean_text(tags.get("name"))
        if highway and street_name:
            if osm_id not in seen_streets:
                seen_streets.add(osm_id)
                streets.append(
                    StreetRecord(
                        osm_id=osm_id,
                        name=street_name,
                        lat=lat,
                        lon=lon,
                        source=source_name,
                    )
                )

        house_number = _clean_text(tags.get("addr:housenumber"))
        addr_street = _clean_text(tags.get("addr:street"))
        if house_number:
            address_bits = [bit for bit in [addr_street, house_number, "Москва"] if bit]
            full_address = ", ".join(address_bits)
            if osm_id not in seen_houses:
                seen_houses.add(osm_id)
                houses.append(
                    HouseRecord(
                        osm_id=osm_id,
                        house_number=house_number,
                        street_name=addr_street,
                        full_address=full_address,
                        lat=lat,
                        lon=lon,
                        source=source_name,
                    )
                )

    return streets, houses


def _load_to_neo4j(streets: list[StreetRecord], houses: list[HouseRecord]) -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    with driver.session() as session:
        session.run("MERGE (:City {name: 'Москва'})")

        for street in streets:
            session.run(
                """
                MATCH (c:City {name: 'Москва'})
                MERGE (s:Street {id: $id})
                SET s.name = $name, s.lat = $lat, s.lon = $lon, s.source = $source
                MERGE (s)-[:IN_CITY]->(c)
                """,
                {
                    "id": f"street:{street.osm_id}",
                    "name": street.name,
                    "lat": street.lat,
                    "lon": street.lon,
                    "source": street.source,
                },
            )

        for house in houses:
            session.run(
                """
                MATCH (c:City {name: 'Москва'})
                MERGE (a:Address {id: $id})
                SET a.full_address = $full_address,
                    a.house_number = $house_number,
                    a.lat = $lat,
                    a.lon = $lon,
                    a.source = $source
                MERGE (a)-[:IN_CITY]->(c)
                """,
                {
                    "id": f"address:{house.osm_id}",
                    "full_address": house.full_address,
                    "house_number": house.house_number,
                    "lat": house.lat,
                    "lon": house.lon,
                    "source": house.source,
                },
            )

            if house.street_name:
                session.run(
                    """
                    MATCH (a:Address {id: $address_id})
                    MERGE (s:Street {name: $street_name})
                    MERGE (a)-[:ON_STREET]->(s)
                    """,
                    {
                        "address_id": f"address:{house.osm_id}",
                        "street_name": house.street_name,
                    },
                )

    driver.close()


def _coords_from_element(element: dict) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return _to_float(element.get("lat")), _to_float(element.get("lon"))
    center = element.get("center")
    if isinstance(center, dict):
        return _to_float(center.get("lat")), _to_float(center.get("lon"))
    return None, None


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
