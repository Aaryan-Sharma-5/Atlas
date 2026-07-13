"""Read-only helper for resolving relationship attachment targets post-resolution."""

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER


def resolve_target(
    entity_id: str,
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> str:
    """Canonical id if entity_id was merged/tentatively merged, else entity_id unchanged.

    Not every :Entity has a :Canonical (cohesion orphans, or entities with no duplicate to resolve against) - see docs/architecture.md Resolution section. Callers attaching relationships must go through this rather than assuming every target is a Canonical.
    """
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            record = session.run(
                "MATCH (c:Canonical)-[:SAME_AS]->(:Entity {id: $id}) "
                "RETURN c.id AS cid LIMIT 1",
                id=entity_id,
            ).single()
            return record["cid"] if record else entity_id
    finally:
        driver.close()
