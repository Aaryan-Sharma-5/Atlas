# CONTRIBUTING.md

Instructions for any developer or AI agent working in this repository. Read this before touching any file.

## Project Identity

**Atlas** is an Enterprise Knowledge Intelligence Platform. It ingests documents, papers, and code repositories, extracts entities and relationships, resolves duplicates, constructs a Neo4j knowledge graph, and answers questions using hybrid retrieval (graph + vector + keyword) with full explainability.

It is not a RAG chatbot. Do not simplify it into one. Every architectural decision below exists to preserve that distinction.

## Non-Negotiable Architectural Rules

1. **Extraction never touches Neo4j directly.** All extraction output must be an internal `Entity` or `Relationship` object from `models/`. Only `graph/builders/` is allowed to construct Cypher.
2. **Schema is documentation-first.** Any new node or relationship type requires an update to `graph/schema/conceptual.md` and `graph/schema/physical.md` before code is written.
3. **No insertion without validation.** Every `Entity`/`Relationship` must pass through `graph/validators/` before reaching `graph/builders/`. Validation checks: duplicate IDs, orphan nodes, missing required properties, invalid confidence range, invalid relationship type.
4. **Confidence and provenance are mandatory fields.** No edge or node is created without `confidence: float`, `extraction_source: string`, `extraction_method: string`.
5. **Node types follow the hierarchy**, even though Neo4j doesn't enforce inheritance:
   - `Resource` → Document, Repository, Paper, Website
   - `CodeEntity` → Module, Class, Function, Interface
   - `KnowledgeEntity` → Technology, API, Dataset, Organization, Person
   New types must be classified under one of these three before implementation.
6. **Entity resolution runs before relationship extraction**, never after. Do not build relationship extraction logic on top of unresolved entity nodes.
7. **Retrieval is planner-first.** No query hits vector search or graph traversal directly. Every query passes through `planner/` to classify: graph-only, vector-only, or hybrid.
8. **Resolution never touches Neo4j and never destructively merges.** `resolution/` reads entities via `graph/queries/`, produces `ResolutionDecision` objects, and writes nothing directly. Duplicates become `Canonical` nodes connected by `SAME_AS` edges to their source entities, never a physical merge that deletes or overwrites a source node. Only `graph/builders/` executes the `SAME_AS` writes, after validation.

## Folder Structure and Ownership

```
atlas/
├── docs/                   # architecture.md, RFC-style design doc
├── graph/
│   ├── schema/             # conceptual.md, physical.md, constraints.cypher, indexes.cypher
│   ├── builders/           # Entity objects -> Cypher, ONLY place that writes to Neo4j
│   ├── queries/            # read-only Cypher query templates
│   └── validators/         # pre-insertion validation logic
├── ingestion/              # PDF, DOCX, GitHub, Markdown parsers
├── extraction/             # NER, relationship extraction -> returns Entity/Relationship objects
├── resolution/             # entity resolution: normalization, blocking, candidate generation, matching, decisioning
│   ├── normalization/      # raw string -> normalized string (case, punctuation, suffixes, whitespace)
│   ├── blocking/           # candidate generation: reduces O(n²) comparisons to O(n) blocks before matching
│   ├── matchers/           # string_matcher.py, embedding_matcher.py -> scored CandidatePair objects
│   └── decisioning/        # merge_resolver.py -> ResolutionDecision objects (MERGE / TENTATIVE / NONE)
├── models/                 # internal Entity, Relationship, dataclasses. Everything imports from here
├── retrieval/              # vector search, graph traversal, hybrid combination
├── planner/                # query classifier: graph vs vector vs hybrid
├── explainability/         # reasoning path tracker, evidence assembly
├── workers/                # incremental update jobs, delta processing
├── api/                    # FastAPI routes
├── frontend/               # React + Cytoscape.js
└── examples/               # fixed test corpus + expected_output/ for regression testing
```

Rule: if you're writing code that imports `neo4j` outside of `graph/builders/` or `graph/queries/`, stop. That's a violation of rule 1.

## Data Flow Contract

```
Raw input (PDF/DOCX/GitHub/Markdown)
    -> ingestion/          (parsing, chunking)
    -> extraction/         (returns models.Entity, models.Relationship)
    -> resolution/normalization/   (raw -> normalized string per entity)
    -> resolution/blocking/        (candidate generation, avoids O(n²) full pairwise comparison)
    -> resolution/matchers/        (string + embedding similarity on blocked candidates -> CandidatePair)
    -> resolution/decisioning/     (CandidatePair -> ResolutionDecision: MERGE / TENTATIVE / NONE)
    -> graph/validators/   (reject or pass)
    -> graph/builders/     (Entity -> Cypher, ResolutionDecision -> Canonical + SAME_AS Cypher)
    -> Neo4j
```

Query side:

```
User question
    -> planner/            (classify: graph | vector | hybrid)
    -> retrieval/          (execute chosen strategy)
    -> explainability/     (assemble reasoning path: nodes visited, chunks retrieved, confidence)
    -> LLM (final answer synthesis with citations)
```

## Coding Conventions

- Python, FastAPI backend. Type hints mandatory on all function signatures.
- No boilerplate. No verbose docstrings restating the function name. Comment only non-obvious logic.
- Entity and Relationship dataclasses live in `models/entity.py` and `models/relationship.py`. Do not redefine them elsewhere.
- Cypher queries are parameterized. No string-interpolated Cypher, ever, regardless of source trust level.
- Tests validate against `examples/expected_output/`, not against hand-checked output. If extraction logic changes, `expected_output/` must be deliberately updated, not silently regenerated.
- Intermediate computation performed during ingestion or extraction (chunk text, chunk offsets, computed statistics like mention counts, generated embeddings) is persisted by default. Discarding an intermediate value requires an explicit one-line justification in a code comment at the point of discard, not silent omission. (Added after the third recurrence of a discarded intermediate needing full-corpus re-derivation to recover: mention_count, embedding vectors, chunk provenance.)

## Build Order (Do Not Reorder)

1. Schema docs (conceptual + physical) written before any code
2. Neo4j + Postgres running, folder structure created
3. One ingestion path working (PDF)
4. Entity extraction (spaCy or LLM-based)
5. Internal Entity/Relationship objects (no Neo4j yet)
6. Entity resolution, in strict sub-order:
   1. Normalization (case, punctuation, legal suffixes, whitespace) before any similarity scoring
   2. Blocking (candidate generation) before matching, never full O(n²) pairwise comparison
   3. String similarity matching on blocked candidates
   4. Embedding similarity matching, only on pairs blocking/string matching did not already pair
   5. Merge decisioning -> `ResolutionDecision` objects (MERGE / TENTATIVE SAME_AS / NONE), storage-agnostic
   6. Canonical + `SAME_AS` graph writes via `graph/builders/`, never a destructive merge
7. Relationship extraction with provenance
8. Graph builder + validation
9. Neo4j insertion
10. Hybrid retrieval
11. Query planner
12. Natural language to Cypher
13. Explainability engine
14. Incremental updates
15. Knowledge quality analytics

Skipping ahead (e.g. building the query planner before entity resolution works) produces a graph the planner can't reason about correctly. Do not do this even if it seems faster.

## Resolution Architecture

Entity resolution is storage-agnostic end to end, same principle as extraction (Rule 1) applied to a different stage.

```
Entity (from graph/queries/, read-only)
    -> normalization/      (raw -> normalized, no scoring yet)
    -> blocking/            (candidate generation: same first letter, same token count, same normalized prefix, or similar cheap key)
    -> matchers/            (string_matcher.py, embedding_matcher.py -> CandidatePair)
    -> decisioning/         (merge_resolver.py -> ResolutionDecision)
    -> graph/validators/    (same validation path as any other write)
    -> graph/builders/      (ResolutionDecision -> Canonical node + SAME_AS edges)
```

**Normalization is mandatory before scoring.** Strip case, punctuation, repeated whitespace, common legal suffixes (Inc., Ltd., LLC), and possessives before any RapidFuzz or embedding comparison runs. Similarity thresholds are calibrated against normalized input, not raw input. If normalization logic changes, thresholds must be recalibrated and `examples/expected_output/resolution_pairs.json` regenerated deliberately.

**Blocking is mandatory before matching**, regardless of current corpus size. Do not compare every entity pair of the same type; generate candidate pairs via a cheap blocking key first (first letter, token count, normalized prefix, phonetic key, or similar), then run RapidFuzz only within blocks. This applies even when the graph is small enough that full pairwise comparison would technically finish in reasonable time. Build the scalable version now, not when the corpus grows past the point where it hurts.

**Merges are never destructive.** A `ResolutionDecision` with `action="MERGE"` or `action="TENTATIVE"` results in a `Canonical` node connected to each source entity via a `SAME_AS` edge. Source entities with their original IDs, confidence, and provenance remain in the graph unchanged. Physical node collapse is not implemented and requires explicit instruction before being added.

**Entity ID convention:** `{type_prefix}_{name_slug}__{source_slug}` pre-resolution. Identical names across sources exist as distinct nodes by design; they are merged explicitly via `resolution/`, never implicitly at write time. Canonical post-resolution IDs drop the source namespace. Full convention documented in `graph/schema/physical.md`.

**Known extraction limitation (recorded as technical debt, not fixed in Phase 2):** `en_core_web_sm` is a general-purpose NER model and under-extracts technical entity types (Technology, Language) relative to Person and Organization. Do not attempt to correct this via resolution logic. A domain-specific extraction strategy is deferred to a later phase and requires explicit instruction.

## Explicitly Out of Scope (Do Not Add Without Explicit Instruction)

- Kubernetes, Kafka, Terraform, microservices
- Multi-agent orchestration for extraction/validation
- Graph versioning (git-like history)
- Full observability stack (Prometheus/Grafana) before Phase 6

These were evaluated and rejected as low interview value relative to engineering cost. Do not reintroduce them because they seem technically interesting.

## When Extending the Schema

1. Update `graph/schema/conceptual.md` (relationships only, no properties)
2. Update `graph/schema/physical.md` (properties, types)
3. Add `CREATE CONSTRAINT` / `CREATE INDEX` to `graph/schema/constraints.cypher` and `indexes.cypher`
4. Only then implement extraction/builder logic

## Testing Philosophy

Every feature is validated against the same fixed corpus in `examples/`. No feature is considered done until it produces output matching (or deliberately updating) `examples/expected_output/`. Random ad hoc document testing is not acceptable for regression purposes.

Resolution specifically is not considered done on a qualitative "looks right" basis. Report quantitatively: raw entity count, canonical entity count post-resolution, reduction percentage, manual precision sample, average aliases per canonical entity, and cross-source canonical entity count. These numbers are the deliverable, not just the merged graph.