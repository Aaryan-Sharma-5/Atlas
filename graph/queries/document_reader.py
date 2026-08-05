"""Read-only Resource display-metadata lookups. Added Step 13C: a Chunk's source_id names its owning Paper/Markdown/Repository/Website by internal id (e.g. "paper_2003_02320v6_pdf"), but nothing in retrieval/ or planner/ ever fetches that resource's title — evidence would otherwise be presented under an internal id string rather than a human-readable title.

Repository has no `title` property (physical.md: Repository carries `name`, not `title`) — coalesced here so one lookup covers all four Resource types uniformly.
"""

from neo4j import GraphDatabase

from graph.builders.neo4j_writer import DEFAULT_PASSWORD, DEFAULT_URI, DEFAULT_USER

_TITLES_QUERY = (
    "MATCH (n) WHERE n.id IN $ids AND (n:Paper OR n:Markdown OR n:Repository OR n:Website) "
    "RETURN n.id AS id, coalesce(n.title, n.name) AS title"
)


def fetch_source_titles(
    source_ids: list[str],
    uri: str = DEFAULT_URI,
    user: str = DEFAULT_USER,
    password: str = DEFAULT_PASSWORD,
) -> dict[str, str]:
    """source_id -> display title, for whichever of the given ids resolve to a Paper/Markdown/Repository/Website. Missing/untitled ids are simply absent from the returned dict, not an error — evidence assembly falls back to the raw id."""
    if not source_ids:
        return {}
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        with driver.session() as session:
            rows = session.run(_TITLES_QUERY, ids=list(set(source_ids)))
            return {r["id"]: r["title"] for r in rows if r["title"]}
    finally:
        driver.close()
