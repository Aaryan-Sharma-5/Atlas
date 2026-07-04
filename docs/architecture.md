# Atlas: Enterprise Knowledge Intelligence Platform
## Architecture and Design Document

## 1. Problem Statement

Organizations accumulate vast amounts of knowledge scattered across documents, research papers, code repositories, wikis, and documentation. Existing retrieval systems (traditional RAG, search engines) treat knowledge as isolated chunks without understanding their relationships:

- **Traditional RAG** retrieves semantically similar text but loses structural relationships (authorship, citations, dependencies, implementations).
- **Search engines** find keyword matches but cannot reason about implicit connections (which papers build on which methods, which functions call which, who built what technology).
- **Enterprise search** lacks graph-based reasoning and explainability — users cannot see *why* a result was returned or trace the evidence chain.

**Result:** Knowledge workers spend time manually connecting facts across sources rather than asking questions and receiving reasoned answers with full provenance.

## 2. Functional Requirements

### MVP (Phase 1-4)
1. **Multi-source ingestion:** Parse PDFs, DOCX files, Markdown, GitHub repositories, and web URLs into normalized chunks with metadata.
2. **Entity extraction:** Identify named entities (people, organizations, technologies, code entities) with NER and relationship extraction.
3. **Entity resolution:** Merge duplicate entities (e.g., "OpenAI" / "openai" / "OpenAI Inc.") while preserving distinct versions ("GPT-4" vs "GPT-4 Turbo").
4. **Relationship extraction:** Build a graph of relationships (authored by, cites, depends on, calls, implements) with confidence scores and provenance.
5. **Neo4j knowledge graph:** Store entities and relationships with full schema (types, properties, constraints, indexes).
6. **Hybrid retrieval:** Answer queries using graph traversal + vector similarity + keyword search.
7. **Query planning:** Route questions to the appropriate retrieval strategy (graph-only, vector-only, hybrid).
8. **Explainability:** Return reasoning paths (nodes visited, chunks retrieved, confidence scores, sources) alongside answers.
9. **REST API:** Expose ingestion, search, and analytics endpoints.
10. **React UI:** Visualize the knowledge graph, search, and chat with explanations.

### Phase 5 (Optional)
- Incremental update processing (delta ingestion).
- Knowledge quality analytics (orphan detection, confidence distributions, duplicate metrics).

### Phase 6 (Optional)
- Redis caching and background jobs.
- Docker Compose orchestration.
- GitHub Actions CI/CD.
- Grafana dashboards.

## 3. Non-Functional Requirements

| Requirement | Target | Rationale |
|---|---|---|
| **Query latency** | < 500ms for graph-only queries; < 2s for hybrid | User-facing search must be responsive |
| **Extraction accuracy** | > 85% entity F1, > 80% relationship precision | Garbage in, garbage out; low precision pollutes the graph |
| **Ingestion throughput** | 100 PDFs/hour on a single machine | Reasonable batch processing speed |
| **Vector embedding latency** | < 100ms per document chunk | Async processing acceptable for embedding pipeline |
| **Neo4j query throughput** | > 1000 Cypher queries/second | Graph traversal must not bottleneck retrieval |
| **Explainability** | Every answer includes: nodes visited, chunks retrieved, confidence, source | Non-negotiable for enterprise trust |
| **Availability** | 99% uptime (Phase 6+) | Production-grade reliability post-MVP |
| **Data consistency** | ACID guarantees for graph writes | Incremental updates must not corrupt the graph |

## 4. System Architecture

### 4.1 High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Ingestion Layer                                             │
│ ├─ PDF Parser (PyPDF2 / pdfplumber)                         │
│ ├─ DOCX Parser (python-docx)                                │
│ ├─ GitHub Parser (GitPython / GitHub API)                   │
│ ├─ Markdown Parser (markdown-it-py)                         │
│ └─ Web Parser (BeautifulSoup)                               │
└─────────────────────────────────────────────────────────────┘

  NOTE (implementation status): ingestion/github_parser.py currently extracts DOCUMENTATION FILES ONLY (.md/.rst prose) plus repo metadata(name, url, pinned commit hash). AST parsing, dependency graphs, and call graphs and are NOT implemented.Code entities (Function, Class, Module) do not yet appear in the graph.     
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Text Processing                                             │
│ ├─ Chunking (token-based, semantic)                         │
│ ├─ Cleaning (normalization, filtering)                      │
│ └─ Metadata extraction (title, author, source)              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Extraction Layer                                            │
│ ├─ spaCy NER → raw entities                                 │
│ ├─ Relationship patterns → raw relationships                │
│ └─ AST parsing (code) → code structure                      │
│ Output: models.Entity, models.Relationship objects          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Resolution Layer                                            │
│ ├─ String similarity (Levenshtein, fuzzy matching)          │
│ ├─ Embedding similarity (Sentence Transformers)             │
│ ├─ Merge decisions (rule-based, ML)                         │
│ └─ Deduplication                                             │
│ Output: Canonical entities, merge provenance               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Validation Layer                                            │
│ ├─ Schema conformance (type checks)                         │
│ ├─ Orphan detection (dangling references)                   │
│ ├─ Confidence validation (0.0-1.0 range)                    │
│ └─ Mandatory field checks                                    │
│ Output: Validated Entity/Relationship objects               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Graph Construction Layer (Neo4j)                            │
│ ├─ Cypher generation (parameterized)                        │
│ ├─ Transaction management                                    │
│ ├─ Constraint/index enforcement                             │
│ └─ Atomic writes                                             │
│ Output: Neo4j nodes and relationships                       │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Query-Time Flow

```
User Question
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Query Planner                                               │
│ ├─ Question classification (entity, relationship, reasoning)│
│ ├─ Required context (graph depth, vector relevance)         │
│ └─ Route decision: graph-only | vector-only | hybrid        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Retrieval Engine                                            │
│ ├─ Graph traversal (Cypher)                                 │
│ ├─ Vector search (embeddings)                               │
│ ├─ Keyword search (full-text index)                         │
│ └─ Hybrid combination (ranked merge)                        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Explainability Engine                                       │
│ ├─ Trace visited nodes                                      │
│ ├─ Aggregate source confidence                              │
│ ├─ Assemble evidence chain                                  │
│ └─ Extract citations                                        │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ LLM Synthesis (optional)                                    │
│ ├─ Ground answer in graph/vector results                    │
│ ├─ Format with citations                                    │
│ └─ Return explanation trail                                 │
└─────────────────────────────────────────────────────────────┘
    ↓
Answer + Reasoning Path + Confidence
```

## 5. Technology Choices and Trade-offs

### 5.1 Graph Database: Neo4j

**Why Neo4j:**
- **Relationship performance:** O(1) traversal cost regardless of graph depth; traditional SQL requires expensive joins.
- **Schema flexibility:** Property graph model supports rich attribute structures without over-normalization.
- **Cypher language:** Declarative query syntax designed for relationship reasoning.
- **Built-in indexes:** Full-text, vector, and B-tree indexes in the same system.

**Trade-off:**
- **Cost:** Neo4j Enterprise is expensive; using Community Edition limits scalability to single-machine deployments (acceptable for MVP).
- **Consistency model:** Eventually consistent in clustered mode; Community Edition is fully ACID but single-instance.

**Alternative considered:** PostgreSQL with graph extension (Apache AGE) — simpler ops but slower traversal, fewer optimizations.

### 5.2 Relational Database: PostgreSQL

**Why PostgreSQL:**
- **pgvector:** Vector search without a separate embedding store.
- **Full-text search:** Built-in TSVector for keyword search.
- **Transactional consistency:** ACID compliance for operational data.
- **JSON support:** Semi-structured data without denormalization.

**Trade-off:**
- **Join overhead:** Will not be the primary query store; Neo4j handles relationships.
- **Role:** PostgreSQL serves as metadata store (document metadata, ingestion job logs, user annotations) and vector search fallback.

**Alternative considered:** Elasticsearch — better for keyword search but overkill for metadata; PostgreSQL + vector indexes suffice for MVP.

### 5.3 NLP and Extraction: spaCy + Sentence Transformers

**Why spaCy:**
- **Production-grade NER:** Fast, accurate English NER out of the box; stateless.
- **No API calls:** Runs locally; no external service dependencies.
- **Extensible:** Can plug in custom matchers, patterns, and models.

**Why Sentence Transformers:**
- **Semantic embeddings:** Superior to TF-IDF for entity resolution and vector search.
- **CPU-friendly:** Quantizable; no GPU required for MVP.
- **Pre-trained on multiple languages:** Flexibility for future multi-language support.

**Trade-off:**
- **LLM extraction accuracy:** Using spaCy + rule-based extraction forgoes the flexibility of LLM-based extraction (e.g., Claude or GPT-4) but trades cost/latency for production speed.
- **LLM approach:** Evaluated; rejected for MVP because:
  - Cost grows linearly with ingestion volume.
  - Latency incompatible with batch processing (100 PDFs/hour requires < 30-40ms/doc).
  - For Phase 2+, LLM-based extraction can be added as a parallel pipeline.

### 5.4 Backend: FastAPI

**Why FastAPI:**
- **Async-native:** Non-blocking I/O for concurrent ingestion, search, and Cypher queries.
- **Automatic OpenAPI docs:** Built-in Swagger UI for API exploration.
- **Performance:** Comparable to Flask + async, faster for typical operations than Django.
- **Type hints:** Automatic validation via Pydantic.

**Alternative considered:** Django — too heavy for this API-first design.

### 5.5 Frontend: React + Cytoscape.js

**Why React:**
- **Component model:** Graph visualization and search UI decompose naturally.
- **Ecosystem:** TailwindCSS for styling, SWR for data fetching, React Query for state management.

**Why Cytoscape.js:**
- **Graph visualization:** Purpose-built for knowledge graph rendering.
- **Interactive layout:** Force-directed, hierarchical, and radial layouts; pan/zoom/select.
- **Lightweight:** Pure JavaScript, no heavy dependencies.

**Trade-off:**
- **Large graphs (> 10,000 nodes):** Will require clustering or viewport filtering for performance. Phase 5 can add incremental rendering.

## 6. API Design (Placeholder)

### 6.1 Ingestion Endpoints

```
POST /api/v1/ingest/pdf
  - Body: multipart file, optional metadata
  - Returns: { ingestion_id, status, entities_found, relationships_found }

POST /api/v1/ingest/repository
  - Body: { github_url, branch }
  - Returns: { ingestion_id, status, code_entities_found }

GET /api/v1/ingest/{ingestion_id}
  - Returns: { status, progress, error_log }
```

### 6.2 Search Endpoints

```
POST /api/v1/search
  - Body: { query, mode: "graph|vector|hybrid" }
  - Returns: { 
      results: [ { node_id, label, confidence, source } ],
      explanation: { nodes_visited, chunks_retrieved, reasoning },
      confidence: float
    }

GET /api/v1/entity/{entity_id}
  - Returns: { id, type, properties, related_entities, relationships }

GET /api/v1/relationship/{relationship_id}
  - Returns: { source_id, target_id, type, confidence, extraction_source }
```

### 6.3 Graph Endpoints

```
GET /api/v1/graph/subgraph
  - Query: { entity_ids: [], depth: int, include_relationships: bool }
  - Returns: { nodes: [], edges: [], layout_hints: {} }

GET /api/v1/graph/stats
  - Returns: { node_count, relationship_count, entity_types, confidence_distribution }
```

### 6.4 Analytics Endpoints

```
GET /api/v1/analytics/quality
  - Returns: { orphan_nodes, duplicate_candidates, confidence_distribution }

GET /api/v1/analytics/ingestion
  - Returns: { documents_processed, entities_extracted, extraction_accuracy }
```

Full endpoint specification will be formalized in Phase 2 after schema finalization.

## 7. Schema Overview

See `graph/schema/conceptual.md` (relationships) and `graph/schema/physical.md` (properties).

**Key principles:**
- All entities carry `confidence`, `extraction_source`, `extraction_method`.
- All relationships carry the same mandatory provenance fields.
- Node types follow the hierarchy: Resource, CodeEntity, KnowledgeEntity.
- No cyclic relationships; relationship directions are semantically meaningful.

## 8. Deployment Model (MVP)

```
Single-machine deployment:
  - Neo4j Community Edition (7474, 7687)
  - PostgreSQL (5432)
  - FastAPI (8000)
  - React dev server or static build (5173)
  - All via Docker Compose
```

**Scalability (Phase 6):**
- Neo4j Enterprise for clustering.
- PostgreSQL read replicas for analytics.
- Redis for caching and job queue.
- Kubernetes for orchestration (if cost-justified).

## 9. Failure Modes and Mitigations

| Failure | Impact | Mitigation |
|---|---|---|
| Extraction produces incorrect entities | Polluted graph, confuses retrieval | Validation layer + confidence thresholds + manual review queue |
| Duplicate entities not merged | Graph fragmentation | Entity resolution validator; confidence penalties for unresolved duplicates |
| Neo4j write transaction fails | Data loss | Transactional integrity; retry logic with exponential backoff |
| Vector search returns irrelevant results | False positives in hybrid retrieval | Graph planner overrides vector-only mode when graph signal is strong |
| LLM hallucination (Phase 4+) | Wrong answers with fake citations | Explicit grounding check: LLM output must cite retrieved nodes |
| Graph grows too large | Query latency degrades | Phase 5 analytics + pruning; Phase 6 sharding |

## 10. Success Metrics

### MVP (Phase 4 completion)
- [ ] Extract ≥ 100 entities from a single research paper with ≥ 80% precision.
- [ ] Resolve ≥ 85% of duplicate entity mentions.
- [ ] Answer ≥ 3 distinct query types (entity lookup, relationship traversal, hybrid) with correct results.
- [ ] Explainability engine traces ≥ 90% of answers to source nodes.

### Phase 5
- [ ] Incremental ingestion of 10 new PDFs adds relationships without re-processing old data.
- [ ] Quality analytics flag ≥ 95% of orphan nodes.

### Phase 6
- [ ] Serve 1000 requests/minute from a 50,000-node graph with p99 latency < 2s.

## 11. Future Extensions (Out of Scope for MVP)

These are explicitly **not** part of the initial build and are listed for architectural completeness:

### 11.1 Advanced NLP and Extraction
- **LLM-based extraction** (Claude, GPT-4) for complex relationships requiring reasoning.
- **Multi-language support** (Sentence Transformers handles this; spaCy would need language-specific models).
- **Domain-specific NER** (e.g., biomedical NER via BioBERT).
- **Aspect-based sentiment extraction** for identifying critical claims or disagreements in papers.

### 11.2 Code Intelligence (Phase 3, explicitly planned)

*Status: none of this exists yet. The current GitHub ingestion path
(`ingestion/github_parser.py`) reads documentation files only.*

- **AST parsing** of entire repositories into call graphs and dependency graphs.
- **Type inference** for function signatures and interfaces.
- **Import resolution** to build a full dependency graph across packages.
- **API documentation extraction** from code comments and type hints.

### 11.3 Advanced Retrieval and Reasoning
- **Sub-graph similarity search** (finding similar patterns, not just similar text).
- **Distributed representation learning** (graph embeddings via GraphSAGE or Node2Vec).
- **Natural language to Cypher** (LLM-powered query generation).
- **Multi-hop reasoning** (X → Y → Z traversals with confidence aggregation).
- **Counterfactual reasoning** (what if we removed this relationship?).

### 11.4 Visualization and UI
- **Interactive graph exploration** (lens/focus mode, degree-of-interest filtering).
- **Timeline views** for papers and technologies (when were they published/introduced?).
- **Diff views** for versioned graphs (what changed in the last ingestion?).
- **Collaborative annotations** (users add context, vote on entity merges).

### 11.5 Operations and Analytics
- **Incremental retraining** of resolution models as user feedback accumulates.
- **Graph anomaly detection** (sudden clusters of low-confidence entities).
- **Cost attribution** (which documents contribute how much value to the graph?).
- **Multi-tenancy** (separate graphs per organization, cross-graph search).

### 11.6 Compliance and Security (Phase 6+)
- **Data lineage tracking** (which extracted facts come from which source documents?).
- **PII detection and redaction** (automatically mask sensitive data).
- **Audit logs** (who queried what, when).
- **Role-based access control** (different users see different subgraphs).

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-01  
**Status:** Architecture frozen; ready for schema definition (Day 1 of Phase 1).
