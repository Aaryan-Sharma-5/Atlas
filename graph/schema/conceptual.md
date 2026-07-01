# Neo4j Conceptual Schema: Atlas Knowledge Graph
## Relationships and Node Hierarchy

This document defines the **conceptual data model**: entity types (hierarchical), relationship types (semantic), and cardinality constraints. It does not specify properties—see `physical.md` for that.

## Node Type Hierarchy

All nodes inherit from one of three base types. Types not listed here are out of scope for MVP.

### Resource Hierarchy

Represents sources of information (documents, papers, code repositories, websites).

```
Resource (abstract base)
├── Document
│   ├── Paper (academic, research paper)
│   └── Markdown (technical documentation, blog post, wiki)
├── Repository (GitHub, GitLab, or similar version control)
└── Website (web pages, documentation sites)
```

**Node counts (typical):** 100-10,000 per ingestion.

### CodeEntity Hierarchy

Represents code structure (extracted via AST parsing). *Phase 3 scope.*

```
CodeEntity (abstract base)
├── Module (Python file, JavaScript module, compiled object)
├── Class (Python class, Java class, TypeScript class)
├── Function (Python function, JavaScript function, method)
├── Interface (TypeScript interface, Java interface, protocol)
├── Variable (global, module-level constants)
└── Type (type alias, struct, dataclass)
```

**Node counts (typical):** 1,000-100,000 per repository, depending on size.

### KnowledgeEntity Hierarchy

Represents concepts and actors in the domain (technologies, organizations, people, datasets, APIs).

```
KnowledgeEntity (abstract base)
├── Technology (programming language, framework, library, tool)
│   ├── Language (Python, Go, JavaScript, etc.)
│   └── Framework (React, FastAPI, Django, etc.)
├── API (REST API, gRPC service, SDK)
├── Dataset (research dataset, benchmark, corpus)
├── Organization (company, research lab, university)
└── Person (researcher, engineer, author)
```

**Node counts (typical):** 100-10,000 per corpus.

---

## Relationship Types

Relationships are typed, directed edges with semantic meaning. They do not form cycles (DAG-like structure preferred). All relationships carry provenance fields (see `physical.md`).

### Authorship and Attribution

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `AUTHORED_BY` | Document, Paper, Repository | Person | 1..N | Person wrote this resource |
| `PUBLISHED_BY` | Paper | Organization | 0..1 | Organization published this paper |
| `AFFILIATED_WITH` | Person | Organization | 0..N | Person was affiliated with this organization |

### Citation and Reference

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `CITES` | Paper | Paper | 0..N | This paper cites another (directional: source → target) |
| `MENTIONS` | Document, Paper, Repository | KnowledgeEntity | 0..N | Generic mention of a concept in a resource |
| `DESCRIBES` | Document, Paper | KnowledgeEntity | 0..N | Explicit description/definition of a concept |

### Technology and Dependency

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `BUILT_BY` | Technology | Organization | 0..1 | Organization created/maintains this technology |
| `BUILT_BY` | API | Organization | 0..1 | Organization provides this API |
| `CREATED_IN` | Technology | Language | 0..1 | Technology is written in this language |
| `EXTENDS` | Technology | Technology | 0..N | Extends/inherits from another technology |
| `DEPENDS_ON` | Technology | Technology | 0..N | Requires this technology as a dependency |

### Code Structure

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `DEFINED_IN` | Function, Class, Variable, Type | Module | 1..1 | Defined in this module |
| `CALLS` | Function | Function | 0..N | Calls this function (or method within a class) |
| `IMPLEMENTS` | Class | Interface | 0..N | Implements this interface |
| `INHERITS_FROM` | Class | Class | 0..1 | Inherits from this class |
| `DEPENDS_ON` | Module, Class | Module | 0..N | Depends on this module |
| `USES_TECHNOLOGY` | Module, Function, Class | Technology | 0..N | Uses this external library/framework |
| `USES_API` | Function, Module | API | 0..N | Calls this API |
| `REFERENCES` | Variable | Type | 0..1 | Has this type (type annotation) |

### Semantic Relationships

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `CONTAINED_IN` | KnowledgeEntity | KnowledgeEntity | 0..N | Part of a larger entity (e.g., method is part of library) |
| `SIMILAR_TO` | KnowledgeEntity | KnowledgeEntity | 0..N | Semantically similar (e.g., two competing technologies) |
| `ALTERNATIVE_TO` | Technology | Technology | 0..N | Alternative/competing solution |

### Dataset and Experimentation

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `EVALUATED_ON` | Technology | Dataset | 0..N | Benchmarked/tested on this dataset |
| `USES_DATASET` | Paper | Dataset | 0..N | Research paper uses this dataset |
| `PRODUCED_BY` | Dataset | Organization | 0..1 | Dataset created by this organization |

### Metadata and Origin

| Relationship | Source | Target | Cardinality | Semantics |
|---|---|---|---|---|
| `EXTRACTED_FROM` | (all entities) | Resource | 1..1 | Entity extracted from this resource (internal tracking) |

---

## Cardinality Notes

- **1..1:** One-to-one; enforced by unique constraint or application logic.
- **0..1:** Optional one-to-one.
- **1..N:** One-to-many; one source can have many targets.
- **0..N:** Zero or more relationships of this type.

Cardinality is **enforced at the application layer** during extraction and validation, not at the Neo4j schema layer.

---

## Relationship Exclusions (Non-Candidates)

The following relationships are **not** modeled as edges for MVP:

- **Temporal relationships** (e.g., "published_date," "updated_on"): These are properties on nodes, not edges.
- **Strength rankings** (e.g., "stronger_than," "less_relevant_than"): Encoded via confidence scores on edges, not as separate relationships.
- **Cross-source same-entity links** (e.g., "same_as"): Handled by entity resolution; not exposed as edges once merged.
- **Negative relationships** (e.g., "does_not_support"): Can be modeled as separate relationship type if required; out of scope for MVP.

---

## Query Patterns (Informational)

This schema supports the following query patterns efficiently in Neo4j:

1. **Entity lookup:** `MATCH (n:Person {name: "Alan Turing"}) RETURN n` — O(1) with index.
2. **Direct relationships:** `MATCH (a:Paper)-[:CITES]->(b:Paper) WHERE a.id = $id RETURN b` — O(1).
3. **1-hop traversal:** `MATCH (n:Technology)<-[:USES_TECHNOLOGY]-(m) RETURN m` — all code that uses this technology.
4. **N-hop traversal:** `MATCH path=(a:Person)-[:AUTHORED_BY*1..3]->(b) RETURN path` — find co-author networks via transitive relationships.
5. **Relationship aggregation:** `MATCH (a:Paper)-[:CITES]->(b:Paper) RETURN b, count(*) as citation_count` — most-cited papers.

---

## Schema Extension Protocol

When adding a new relationship type:

1. **Update this file** (conceptual.md) with the relationship row, source type, target type, and cardinality.
2. **Update physical.md** with any new relationship-level properties.
3. **Implement validation** in `graph/validators/` to enforce cardinality at write time.
4. **Document extraction logic** in `extraction/` that populates the relationship.

**Never** add a relationship type in code without first updating these docs.

---

## Terminology

- **Node type:** The label assigned to a node (e.g., `Person`, `Technology`).
- **Relationship type:** The type of an edge (e.g., `AUTHORED_BY`, `CITES`).
- **Property:** A key-value pair stored on a node or relationship (defined in `physical.md`).
- **Confidence:** A float (0.0-1.0) on every node and relationship indicating extraction confidence (mandatory).
- **Provenance:** Metadata about extraction (source document, method, timestamp).

---

**Document Version:** 1.0  
**Last Updated:** 2026-07-01  
**Status:** Complete for MVP; additional relationship types from Phase 3 (code intelligence) not yet included.
