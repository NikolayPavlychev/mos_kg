from neo4j import GraphDatabase

from app.core.config import get_settings


def run_sample_ingest() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    city_name = "Москва"
    districts = ["Тверской", "Арбат", "Пресненский"]
    metro = ["Охотный Ряд", "Арбатская", "Белорусская"]

    with driver.session() as session:
        session.run("MERGE (c:City {name: $name})", {"name": city_name})

        for district in districts:
            session.run(
                """
                MERGE (d:District {name: $district_name})
                WITH d
                MATCH (c:City {name: $city_name})
                MERGE (d)-[:PART_OF]->(c)
                """,
                {"district_name": district, "city_name": city_name},
            )

        for station in metro:
            session.run("MERGE (m:MetroStation {name: $station})", {"station": station})

    driver.close()
