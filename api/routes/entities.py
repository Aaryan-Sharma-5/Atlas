"""GET /api/v1/entities/{id} and /api/v1/entities/{id}/graph (Step 14B). Thin transport only — the detail route calls graph/queries/entity_reader.py's fetch_entity_detail(), the graph route calls retrieval/graph_retriever.py's get_entity_context() directly (the same retriever /query's graph routing uses, not new Cypher). No routing/retrieval logic belongs here.
"""

from fastapi import APIRouter, HTTPException, Query

from api.schemas import EntityDetailResponse, EntityGraphResponse
from graph.queries.entity_reader import fetch_entity_detail
from retrieval.graph_retriever import get_entity_context

router = APIRouter(prefix="/api/v1", tags=["entities"])

# repo_rdflib_rdflib alone has 666 one-hop relationships (confirmed live) — an unbounded neighborhood dump is impractical for a single response or a Cytoscape render. 100 is a starting default or, since `truncated` on the response tells the caller more exists; raise up to 500 via the query param when a caller genuinely wants a bigger slice.
_DEFAULT_GRAPH_LIMIT = 100
_MAX_GRAPH_LIMIT = 500


@router.get("/entities/{entity_id}", response_model=EntityDetailResponse)
def get_entity(entity_id: str) -> EntityDetailResponse:
    detail = fetch_entity_detail(entity_id)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"No entity or canonical found with id {entity_id!r}."
        )
    return EntityDetailResponse.from_detail(detail)


@router.get("/entities/{entity_id}/graph", response_model=EntityGraphResponse)
def get_entity_graph(
    entity_id: str,
    relationship_types: list[str] | None = Query(default=None),
    limit: int = Query(default=_DEFAULT_GRAPH_LIMIT, ge=1, le=_MAX_GRAPH_LIMIT),
) -> EntityGraphResponse:
    try:
        results = get_entity_context(entity_id, relationship_types=relationship_types)
    except ValueError as exc:
        # unknown relationship type in the query param — same treatment as /query's graph_seed_id gap: a documented input-validation failure, not a 500.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not results:
        raise HTTPException(status_code=404, detail=f"No entity found with id {entity_id!r}.")

    return EntityGraphResponse.from_results(entity_id, results, limit=limit)
