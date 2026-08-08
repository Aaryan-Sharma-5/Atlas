"""POST /api/v1/query (Step 14A). Thin transport only — calls plan_and_retrieve() + assemble_explained_answer() and maps the result to QueryResponse. No retrieval/planner/ graph logic belongs here (CLAUDE.md); if this handler starts making routing decisions, that's a bug, not a feature.
"""

from fastapi import APIRouter, HTTPException

from api.schemas import QueryRequest, QueryResponse
from explainability.explained_answer import assemble_explained_answer
from planner.planner import plan_and_retrieve

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    try:
        routing = plan_and_retrieve(request.question, top_k=request.top_k)
    except ValueError as exc:
        # graph routing without a graph_seed_id (planner/planner.py) — free-text entity linking isn't implemented in Atlas yet; this is a documented scoping gap (planner/planner.py module docstring), not an unexpected failure.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    explained = assemble_explained_answer(request.question, routing)
    if explained is None:
        raise HTTPException(status_code=404, detail="No results found for this question.")

    return QueryResponse.from_explained_answer(explained)
