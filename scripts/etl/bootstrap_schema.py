from neo4j import GraphDatabase

from app.core.config import get_settings


def run_schema_bootstrap() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    schema_queries = [
        "CREATE CONSTRAINT city_name_unique IF NOT EXISTS FOR (c:City) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT district_name_unique IF NOT EXISTS FOR (d:District) REQUIRE d.name IS UNIQUE",
        "CREATE CONSTRAINT metro_station_name_unique IF NOT EXISTS FOR (m:MetroStation) REQUIRE m.name IS UNIQUE",
        "CREATE CONSTRAINT category_name_unique IF NOT EXISTS FOR (c:Category) REQUIRE c.name IS UNIQUE",
        "CREATE CONSTRAINT organization_id_unique IF NOT EXISTS FOR (o:Organization) REQUIRE o.id IS UNIQUE",
        "CREATE CONSTRAINT place_id_unique IF NOT EXISTS FOR (p:Place) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT address_full_address_unique IF NOT EXISTS FOR (a:Address) REQUIRE a.full_address IS UNIQUE",
        "CREATE INDEX district_name_idx IF NOT EXISTS FOR (d:District) ON (d.name)",
        "CREATE INDEX metro_station_name_idx IF NOT EXISTS FOR (m:MetroStation) ON (m.name)",
        "CREATE INDEX organization_name_idx IF NOT EXISTS FOR (o:Organization) ON (o.name)",
        "CREATE INDEX category_name_idx IF NOT EXISTS FOR (c:Category) ON (c.name)",
    ]

    with driver.session() as session:
        for query in schema_queries:
            session.run(query)

    driver.close()
