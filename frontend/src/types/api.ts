// Mirrors api/schemas.py field-for-field. Verified against live /api/v1/query and /api/v1/entities/{id} responses before writing this file (Step 14C Step 0) — not a guessed shape. Two things worth calling out for anyone extending this later:
// - `evidence` on QueryResponse is a SINGLE object, not a list. There is exactly one evidence item per answer today (explainability/explained_answer.py explains one ranked result at a time), even though the shape can itself describe zero, one, or linked chunk content depending on `shape`.
// - `per_source_contributions` / `graph_traversal_path` are untyped dicts on the backend (list[dict] in api/schemas.py) — kept as Record<string, unknown>[] here rather than invented interfaces, since the backend itself doesn't commit to a fixed shape for them.

export interface QueryRequest {
  question: string;
  top_k?: number;
}

export type EvidenceShape = "entity_with_chunk" | "chunk_is_answer" | "entity_only";

export interface EvidenceOut {
  shape: EvidenceShape;
  chunk_id: string | null;
  chunk_content: string | null;
  chunk_index: number | null;
  source_document_id: string | null;
  source_document_title: string | null;
}

export interface CaveatOut {
  section: string;
  label: string;
}

export interface QueryResponse {
  question: string;
  answer_entity_id: string;
  answer_display_text: string;
  answer_type: string;
  target_resolution: string;

  evidence: EvidenceOut;

  routing_decision: string;
  relationship_type_filtered: string[] | null;
  retrievers_invoked: string[];
  single_strategy_vs_fused: boolean;
  per_source_contributions: Record<string, unknown>[] | null;
  graph_traversal_path: Record<string, unknown>[];

  confidence_score: number;
  confidence_method: string;
  confidence_label: string;

  known_limitations: CaveatOut[];
}

export interface AliasOut {
  id: string;
  name: string | null;
  confidence: number | null;
  decision_action: string | null;
}

// Not rendered by any F1 component yet (no entity panel until F3) — typed now per instruction, kept in sync with api/schemas.py::EntityDetailResponse.
export interface EntityDetailResponse {
  id: string;
  node_type: string | null;
  is_canonical: boolean;
  name: string | null;
  confidence: number;
  extraction_source: string;
  extraction_method: string;
  properties: Record<string, unknown>;
  aliases: AliasOut[];
}

// Shape of the JSON body FastAPI's HTTPException handler returns on 4xx (query.py, entities.py both raise HTTPException(status_code=..., detail=str)) — verified live against /api/v1/query with no graph_seed_id support (422) in the prior session.
export interface ApiErrorBody {
  detail: string;
}

// Mirrors api/schemas.py::GraphNodeOut/GraphEdgeOut/EntityGraphResponse — the GET /entities/{id}/graph shape (Step 14D, F2).
export interface GraphNodeOut {
  id: string;
  label: string;
  type: string | null;
  target_resolution: string;
}

export interface GraphEdgeOut {
  source: string;
  target: string;
  relationship_type: string;
  direction: string;
}

export interface EntityGraphResponse {
  nodes: GraphNodeOut[];
  edges: GraphEdgeOut[];
  truncated: boolean;
}
