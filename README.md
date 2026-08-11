# Atlas | Enterprise Knowledge Intelligence Platform

Atlas ingests documents, research papers, and code repositories, resolves duplicate entities, and builds a Neo4j knowledge graph that answers questions through graph traversal, vector search, and keyword search — with every answer's reasoning path exposed.

Traditional RAG systems answer questions by retrieving similar chunks. Atlas answers questions by traversing relationships (authorship, mention, canonical identity) combined with vector and keyword search where semantic similarity is what the question actually needs. There is no LLM synthesis step: an answer's display text comes directly from the retrieved entity name or chunk text, and the explainability layer reports exactly which retriever produced it and why. This is a deliberate scope boundary, not a missing feature;  see [Deliberately Deferred](#deliberately-deferred).

## Architecture

```
Ingestion (PDF / Markdown / GitHub docs)
        ↓
Extraction (spaCy NER → internal Entity/Relationship objects)
        ↓
Resolution (normalize → block → match → decide → Canonical + SAME_AS)
        ↓
Validation (graph/validators/)
        ↓
Graph Construction (Neo4j — entities, canonicals, relationships, chunks, embeddings)
        ↓
Hybrid Retrieval (graph traversal + vector search + keyword search)
        ↓
Query Planner (classify: graph / vector_name / vector_passage / keyword / hybrid)
        ↓
Explainability (evidence, routing decision, confidence method, caveats)
        ↓
FastAPI → React + Cytoscape.js frontend
```

Full data flow, design rationale, and every scoping decision behind these boxes: [docs/architecture.md](docs/architecture.md).

## Core Capabilities

| Capability | Status |
|---|---|
| Ingestion | PDF (metadata + text), Markdown, GitHub repositories (documentation files only — `.md`/`.rst`, source code not parsed) |
| Entity extraction | spaCy NER (`en_core_web_sm`) → internal `Entity` objects. Under-extracts Technology/Language relative to Person/Organization — recorded technical debt, not corrected in resolution |
| Entity resolution | Normalize → block → string match (RapidFuzz) → embedding match (all-MiniLM-L6-v2) → decision. Non-destructive: `Canonical` nodes connected to sources via `SAME_AS`, never a physical merge |
| Relationship extraction | `AUTHORED_BY` (Paper→Person) and `MENTIONS` (Paper/Markdown/Repository→KnowledgeEntity) are live, written, and idempotency-verified. `MENTIONS` (Repository→API) and `USES` (Repository→Technology) are blocked pending code intelligence — see Deferred |
| Hybrid retrieval | Graph traversal (1-hop, relationship-type-filtered), vector search (name and passage modes against Neo4j native vector indexes), keyword search (Lucene fulltext), fused via canonical-aware Reciprocal Rank Fusion |
| Query planner | Classifies each question into graph / vector_name / vector_passage / keyword / hybrid and routes accordingly; infers relationship-type filters from question language |
| Explainability | Every answer carries its evidence, routing decision, retrievers invoked, confidence score + method, and applicable caveats (e.g. PDF encoding risk, low-coverage quality signal) |
| API + frontend | FastAPI (`/api/v1/query`, `/api/v1/entities`) backing a React + Cytoscape.js UI: query bar, answer card, evidence card, interactive graph view, entity panel |

Current graph, from the live corpus: 4,482 `Entity` nodes, 329 `Canonical` clusters (731 entities resolved), 4,224 `MENTIONS` edges (only 11% reachable by resolution quality review — the rest point at unresolved raw entities), 18 `AUTHORED_BY` edges. Resolution thresholds: 0.85 string-match floor, 0.92 auto-merge floor, 0.85 cluster cohesion floor. Full methodology and numbers: [docs/architecture.md §12](docs/architecture.md).

## Deliberately Deferred

Each of these was investigated, not skipped — reasoning and reactivation conditions are in `docs/architecture.md`.

| Deferred | Why | Reactivation condition |
|---|---|---|
| **NL → Cypher** (LLM-generated graph queries) | 8 concrete multi-hop/aggregation questions were run against the live graph before writing any generation code. 1 was a pure data gap, 3 were already answerable by composing existing calls, 3 were closed with fixed parameterized templates (`graph/queries/aggregates.py`), 1 needs a schema field that doesn't exist yet. None needed LLM-generated Cypher. | Lands when Phase 3's code-intelligence relationship types (`CALLS`, `IMPLEMENTS`, `DEPENDS_ON`) give the graph enough multi-hop structure for open-ended traversal to be worth generating queries for |
| **Code intelligence** (AST parsing, call graphs, dependency graphs) | Phase 3, not started. Blocks two relationship sub-phases: `MENTIONS` Repository→API (no `:API`-typed entity can exist without endpoint extraction) and `USES` Repository→Technology (`github_parser.py` never opens manifest files) | Explicit Phase 3 kickoff |
| **Incremental updates** (delta processing on new documents) | Not started — no `workers/` module exists yet. Every ingestion run is currently a full pass | Phase 5 |
| **Knowledge quality analytics** (orphan nodes, graph density, corpus-wide confidence distribution) | Resolution has its own quality-flagging pass (`resolution/quality/`: short-name embedding risk, NER stutter, large tentative clusters, cross-type collisions) but there is no graph-wide analytics layer beyond that | Phase 5 |
| **Answer synthesis via LLM** | Answer text is the retrieved entity name or chunk text, not a generated summary. Kept out deliberately so every word in an answer is traceable to a specific node or chunk — synthesis would break that traceability guarantee | Would require re-deriving the explainability contract from scratch; no current plan to add it |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, TypeScript, Cytoscape.js (`react-cytoscapejs`), Vite |
| Backend | FastAPI |
| Graph Database | Neo4j 5 (native vector indexes + fulltext indexes, no separate vector store) |
| Relational Database | PostgreSQL — provisioned in `docker-compose.yml`, connectivity-tested, not used by any application code path today |
| NLP / Embeddings | spaCy (`en_core_web_sm`), Sentence Transformers (`all-MiniLM-L6-v2`), RapidFuzz |
| Retrieval | Neo4j Cypher (graph), Neo4j vector index (semantic), Neo4j fulltext/Lucene (keyword), Reciprocal Rank Fusion |
| Infra | Docker Compose (Neo4j + Postgres) |

LangChain is not used anywhere in this codebase — it appeared in an earlier planning draft and was dropped.

## Project Structure

```
atlas/
├── docs/               # architecture.md — full design rationale, dated findings, open gaps
├── graph/
│   ├── schema/         # conceptual and physical schema definitions
│   ├── builders/       # internal objects -> Cypher, only place that writes to Neo4j
│   ├── queries/        # read-only Cypher query templates
│   └── validators/     # pre-insertion validation
├── ingestion/           # PDF, Markdown, GitHub (docs-only) parsers
├── extraction/          # entity extraction -> internal Entity objects
├── relationships/       # relationship extraction -> internal Relationship objects
├── resolution/          # normalization, blocking, matching, decisioning, quality flagging
├── models/               # internal Entity/Relationship/ResolutionDecision dataclasses
├── retrieval/            # graph, vector, keyword retrievers + RRF fusion
├── planner/              # query classification and routing
├── explainability/       # evidence, caveats, ExplainedAnswer assembly
├── api/                  # FastAPI routes
├── frontend/              # React + Cytoscape.js application
├── testing/               # pipeline and integration tests
└── examples/              # fixed corpus + expected_output/ for regression testing
```

Engineering rules, build order, and the resolution architecture contract: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Setup

```bash
# Neo4j + Postgres
docker-compose up -d

# Backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Neo4j browser: `http://localhost:7474`
API: `http://localhost:8000`
Frontend: `http://localhost:5173`

`test_connectivity.py` checks both Neo4j and PostgreSQL are reachable after `docker-compose up`.

## Testing

All features are validated against a fixed corpus in `examples/` with expected output in `examples/expected_output/`. Extraction and resolution changes are checked against this corpus rather than ad hoc documents; if extraction or resolution logic changes, `expected_output/` is deliberately regenerated, not silently overwritten. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full testing philosophy.

