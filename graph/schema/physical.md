# Neo4j Physical Schema: Atlas Knowledge Graph
## Node and Relationship Properties

This document specifies the **physical data model**: exact properties, data types, examples, and indexes. It is the single source of truth for what appears in Neo4j.

---

## Mandatory Fields (All Nodes and Relationships)

Every node and relationship **must** have these fields:

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `confidence` | float | ✓ | Extraction confidence, [0.0, 1.0]. | 0.92 |
| `extraction_source` | string | ✓ | Source document or resource identifier. | "pdf:arxiv_2012.14165" |
| `extraction_method` | string | ✓ | How it was extracted (spaCy, regex, LLM, manual, etc.). | "spacy:en_core_web_md" |

These fields prevent data loss and enable source tracing. They are enforced by `graph/validators/` before insertion.

---

## Entity Id Convention

Extraction-produced entity ids follow:

```
{type_prefix}_{name_slug}__{source_slug}
```

| Segment | Meaning | Example |
|---|---|---|
| `type_prefix` | Short prefix per node type (person, org, tech, lang) | `person` |
| `name_slug` | Lowercased, punctuation-collapsed entity name | `aidan_hogan` |
| `source_slug` | Slug of the extraction source document | `2003_02320v6_pdf` |

Full example: `person_aidan_hogan__2003_02320v6_pdf`

**Why the source namespace:** ids are deterministic slugs of names, so the same name extracted from two documents would otherwise collide with the `unique_entity_id` constraint. **Pre-resolution, identical names across sources exist as distinct nodes by design.** Merging them into one canonical entity is `resolution/`'s job — an explicit, auditable step — never an implicit side effect of an id collision at write time.

**Canonical id convention (post-resolution):** canonical entities drop the source namespace:

```
{type_prefix}_{name_slug}
```

`type_prefix` is taken from the member entities (person, org, tech, lang), `name_slug` is the slug of the chosen canonical name. Example: `person_aidan_hogan` canonicalizing `person_aidan_hogan__2003_02320v6_pdf` and `person_aidan_hogan__2002_00388v4_pdf`. If two distinct clusters of the same type slug to the same id, a numeric suffix disambiguates (`person_aidan_hogan_2`) — collision does NOT imply same entity. The examples in this file (e.g. `tech_pytorch`) show the canonical form.

---

## Node Properties by Type

### Resource Hierarchy

#### Document (abstract, never instantiated directly)

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Unique identifier (UUID or hash). | "doc_abc123def456" |
| `title` | string | ✓ | Document title. | "Attention Is All You Need" |
| `authors` | list[string] | ✗ | List of author names. | ["Vaswani, A.", "Shazeer, N."] |
| `source_url` | string | ✗ | Original URL if scraped. | "https://arxiv.org/pdf/1706.03762.pdf" |
| `ingestion_timestamp` | integer | ✓ | Unix timestamp of ingestion. | 1719331200 |
| `file_hash` | string | ✓ | SHA256 of original file (dedup). | "abc123def456..." |
| `page_count` | integer | ✗ | For PDFs. | 15 |
| `language` | string | ✗ | Detected language (ISO 639-1). | "en" |
| `content_type` | string | ✓ | MIME type (application/pdf, etc.). | "application/pdf" |

**Example:**
```json
{
  "id": "doc_arxiv_1706.03762",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
  "source_url": "https://arxiv.org/pdf/1706.03762.pdf",
  "ingestion_timestamp": 1719331200,
  "file_hash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ae8c7e25ad1065bfe2ac37db8c34",
  "page_count": 15,
  "language": "en",
  "content_type": "application/pdf",
  "confidence": 1.0,
  "extraction_source": "pdf:manual_upload",
  "extraction_method": "pdfplumber"
}
```

#### Paper

Extends Document. Additional properties:

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `venue` | string | ✗ | Conference/journal name. | "NeurIPS" |
| `publication_year` | integer | ✗ | Year of publication. | 2017 |
| `abstract` | string | ✗ | Paper abstract. | "The dominant sequence transduction models..." |
| `arxiv_id` | string | ✗ | arXiv identifier. | "1706.03762" |
| `doi` | string | ✗ | Digital Object Identifier. | "10.5555/3295222.3295349" |

#### Markdown

Extends Document. Additional properties:

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `markdown_source` | string | ✗ | Type of markdown (wiki, blog, docstring, etc.). | "wiki" |
| `is_indexed` | boolean | ✗ | Whether indexed in vector search. | true |

#### Repository

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Unique identifier (full GitHub URL or similar). | "repo_github_torvalds_linux" |
| `name` | string | ✓ | Repository name. | "linux" |
| `url` | string | ✓ | Clone/browse URL. | "https://github.com/torvalds/linux" |
| `language` | string | ✗ | Primary language. | "C" |
| `last_commit` | integer | ✗ | Unix timestamp of last commit. | 1719331200 |
| `star_count` | integer | ✗ | GitHub stars (if applicable). | 167000 |
| `description` | string | ✗ | Repository description. | "Linux kernel source tree" |

#### Website

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Unique identifier. | "site_pytorch_docs" |
| `url` | string | ✓ | Full URL. | "https://pytorch.org/docs" |
| `title` | string | ✓ | Page title or site name. | "PyTorch Documentation" |
| `domain` | string | ✓ | Domain (for grouping). | "pytorch.org" |
| `last_crawled` | integer | ✗ | Unix timestamp of last crawl. | 1719331200 |

#### Chunk (Step 9.5, ingestion-derived — see conceptual.md for the "why Resource, not a separate top-level type" reasoning)

Built via the same generic `Entity`/`graph/validators/`/`graph/builders/` path as `Paper`/`Markdown`/`Repository` — carries `:Entity:Resource:Chunk`, covered by the existing `unique_entity_id` constraint, no new constraint needed.

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | `chunk_{source_slug}_{chunk_index}`. | "chunk_2003_02320v6_pdf_47" |
| `content` | string | ✓ | The chunk's raw text. | "Knowledge graphs represent..." |
| `chunk_index` | integer | ✓ | Position within the source's chunk sequence. | 47 |
| `char_start` | integer | ✓ | Start character offset within the source's full text. | 23400 |
| `char_end` | integer | ✓ | End character offset within the source's full text. | 23900 |
| `source_id` | string | ✓ | Id of the owning Document/Paper/Markdown/Repository/Website. Denormalized — also reachable via `HAS_CHUNK` — same pattern as entity ids already embedding their source namespace. | "paper_2003_02320v6_pdf" |
| `embedding` | list[float] | ✗ | 384-dim passage embedding (`all-MiniLM-L6-v2`, embedding-mode chunking — see `ingestion/chunker.py::chunk_text_for_embedding`). Optional: the vector index is created before population (Step 9.5 STEP 1 decision), so Chunk nodes may legitimately exist without it yet. | [0.0123, -0.045, ...] |
| `created_at` | integer | ✓ | Unix timestamp of chunk creation. | 1784332800 |

---

### CodeEntity Hierarchy

#### CodeEntity (abstract, never instantiated)

All code entities share these base properties:

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Unique identifier (FQN or hash). | "func_torch_nn_Linear_forward" |
| `name` | string | ✓ | Simple name (no qualification). | "forward" |
| `fully_qualified_name` | string | ✓ | Fully qualified name (module path). | "torch.nn.modules.linear.Linear.forward" |
| `description` | string | ✗ | Docstring or comment. | "Defines the computation..." |
| `visibility` | string | ✗ | public, private, protected. | "public" |
| `line_number` | integer | ✗ | Source line number. | 120 |

#### Function

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `signature` | string | ✗ | Function signature (with types). | "def forward(self, input: Tensor) -> Tensor:" |
| `return_type` | string | ✗ | Return type annotation. | "Tensor" |
| `parameters` | list[string] | ✗ | Parameter names. | ["self", "input", "hidden"] |
| `is_async` | boolean | ✗ | Whether async/await. | false |

#### Class

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `base_classes` | list[string] | ✗ | Parent class names. | ["torch.nn.Module"] |
| `is_abstract` | boolean | ✗ | Abstract class flag. | false |

#### Interface

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `methods` | list[string] | ✗ | Method signatures. | ["forward(Tensor) -> Tensor"] |

#### Module

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `file_path` | string | ✓ | Relative path in repository. | "torch/nn/modules/linear.py" |
| `is_package` | boolean | ✗ | Whether it's a package (`__init__.py`). | false |

#### Variable

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `var_type` | string | ✗ | Inferred type. | "float" |
| `is_constant` | boolean | ✗ | Constant flag. | true |

#### Type

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `type_definition` | string | ✗ | Type alias or struct definition. | "TypeAlias = Union[Tensor, List[Tensor]]" |

---

### KnowledgeEntity Hierarchy

#### KnowledgeEntity (abstract, never instantiated)

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Unique canonical identifier. | "tech_pytorch" |
| `name` | string | ✓ | Primary name (canonical form). | "PyTorch" |
| `aliases` | list[string] | ✗ | Alternative names (torch, pytorch-lib). | ["torch", "pytorch-lib"] |
| `description` | string | ✗ | Description/definition. | "Deep learning framework..." |
| `name_embedding` | list[float] | ✗ | 384-dim name embedding (`all-MiniLM-L6-v2`, same model Stage 2 resolution already uses for name-similarity matching). Deliberately **not** named `embedding` — `Chunk.embedding` (passage-level semantic search) and this (short name-similarity) are different retrieval use cases; sharing a property name would make `:Entity`-scoped vector indexes ambiguous since `Chunk` also carries `:Entity`. | [0.0456, ...] |

#### Technology

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `category` | string | ✗ | Classification (framework, library, tool, language). | "framework" |
| `version_latest` | string | ✗ | Latest known version. | "2.1.0" |
| `website` | string | ✗ | Official website URL. | "https://pytorch.org" |
| `github_url` | string | ✗ | GitHub repository URL. | "https://github.com/pytorch/pytorch" |
| `license` | string | ✗ | License type. | "BSD-3-Clause" |

#### Language (extends Technology)

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `iso_code` | string | ✗ | ISO 639-1 language code. | "py" |
| `year_released` | integer | ✗ | Year of first release. | 1991 |

#### Framework (extends Technology)

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `supported_languages` | list[string] | ✗ | Languages it targets. | ["Python", "Java"] |

#### API

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `api_type` | string | ✗ | rest, graphql, grpc, sdk. | "rest" |
| `base_url` | string | ✗ | API endpoint base. | "https://api.openai.com/v1" |
| `authentication` | string | ✗ | Auth method (api_key, oauth, etc.). | "api_key" |
| `documentation_url` | string | ✗ | Docs URL. | "https://platform.openai.com/docs" |

#### Dataset

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `size` | integer | ✗ | Number of samples/rows. | 60000 |
| `feature_count` | integer | ✗ | Number of features/columns. | 784 |
| `download_url` | string | ✗ | Download link. | "http://yann.lecun.com/exdb/mnist/" |
| `license` | string | ✗ | Data license. | "CC0" |

#### Organization

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `organization_type` | string | ✗ | company, university, lab, ngo. | "company" |
| `headquarters` | string | ✗ | HQ location. | "San Francisco, CA" |
| `website` | string | ✗ | Official website. | "https://openai.com" |
| `founded_year` | integer | ✗ | Year founded. | 2015 |

#### Person

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `full_name` | string | ✓ | Full name (canonical form). | "Alan M. Turing" |
| `email` | string | ✗ | Email address. | "alan@example.com" |
| `orcid` | string | ✗ | ORCID identifier. | "0000-0000-0000-0000" |
| `homepage` | string | ✗ | Personal website. | "https://example.com" |
| `birth_year` | integer | ✗ | Year of birth. | 1912 |

---

### Canonical (resolution layer)

Derived by `resolution/decisioning/`, never extracted. Labels: `:Canonical:{SpecificType}` (no `:Entity` label — see conceptual.md). Mandatory confidence/provenance fields apply (Rule 4) with resolution semantics: `confidence` is the decision confidence (weakest supporting candidate-pair score in the cluster), `extraction_source` names the candidate set the decision was made from, `extraction_method` names the resolver and its rule version.

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `id` | string | ✓ | Canonical id, `{type_prefix}_{name_slug}` (no source namespace). | "person_aidan_hogan" |
| `canonical_name` | string | ✓ | Chosen display name (most frequent member name; ties → longest). | "Aidan Hogan" |
| `created_at` | integer | ✓ | Unix timestamp of the resolution write. | 1784332800 |
| `source_count` | integer | ✓ | Number of member entities behind this canonical. | 3 |
| `confidence` | float | ✓ | Decision confidence, [0.0, 1.0]. | 0.94 |
| `extraction_source` | string | ✓ | Candidate set provenance. | "resolution:candidate_pairs" |
| `extraction_method` | string | ✓ | Resolver + rule version. | "merge_resolver:union_find@v1" |
| `name_embedding` | list[float] | ✗ | 384-dim name embedding, same use case and same reason for the name (not `embedding`) as `KnowledgeEntity.name_embedding` above. | [0.0456, ...] |

---

## Relationship Properties

All relationships carry these mandatory fields (plus the ones below):

| Property | Type | Required | Description |
|---|---|---|---|
| `confidence` | float | ✓ | Extraction confidence [0.0, 1.0] |
| `extraction_source` | string | ✓ | Source resource identifier |
| `extraction_method` | string | ✓ | How it was extracted |

**Phase 7A target resolution:** for `AUTHORED_BY` (Paper→Person), `MENTIONS` (Document→KnowledgeEntity, Repository→API), and `USES` (Repository→Technology), the relationship is written against `graph.queries.resolve_target.resolve_target(entity_id)`'s return value, not the raw extracted entity id — see conceptual.md's Phase 7A section and `docs/architecture.md` §12.5.

### Authorship and Attribution

#### AUTHORED_BY

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `role` | string | ✗ | Specifics (lead author, contributor, etc.). | "lead_author" |

#### PUBLISHED_BY

No additional properties beyond mandatory fields.

#### AFFILIATED_WITH

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `role` | string | ✗ | Role/title at organization. | "Research Scientist" |
| `start_year` | integer | ✗ | Year affiliation started. | 2015 |
| `end_year` | integer | ✗ | Year affiliation ended (null if current). | null |

---

### Citation and Reference

#### CITES

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `context` | string | ✗ | Surrounding text of citation. | "as shown in [Vaswani et al.]..." |

#### MENTIONS

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `context` | string | ✗ | Text snippet around mention. | "PyTorch is widely used..." |
| `frequency` | integer | ✗ | Number of mentions (if aggregated). | 3 |

#### DESCRIBES

No additional properties beyond mandatory fields.

---

### Technology and Dependency

#### BUILT_BY

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `start_year` | integer | ✗ | Year development started. | 2015 |

#### CREATED_IN

No additional properties.

#### EXTENDS

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `extends_features` | list[string] | ✗ | What features are extended. | ["gradient computation", "autograd"] |

#### DEPENDS_ON

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `version_constraint` | string | ✗ | Version requirement (e.g., >=1.0.0). | ">=2.0.0" |
| `is_optional` | boolean | ✗ | Optional vs. required dependency. | false |

#### USES

Resource-level dependency signal (Repository → Technology, Phase 7A). Distinct relationship from the code-level `USES_TECHNOLOGY` below — see conceptual.md's Phase 7A section for the disambiguation.

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `detected_via` | string | ✗ | Where the dependency signal came from. | "manifest:requirements.txt" |

---

### Code Structure

#### DEFINED_IN

No additional properties.

#### CALLS

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `call_count` | integer | ✗ | Number of calls (if aggregated). | 5 |
| `is_indirect` | boolean | ✗ | Indirect call (via function pointer). | false |

#### IMPLEMENTS

No additional properties.

#### INHERITS_FROM

No additional properties.

#### DEPENDS_ON (Code)

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `import_type` | string | ✗ | import, from...import, require. | "from...import" |

#### USES_TECHNOLOGY

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `version_used` | string | ✗ | Version constraint found in code. | ">=1.0.0" |

#### USES_API

No additional properties.

#### REFERENCES

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `is_annotation` | boolean | ✗ | Whether type annotation. | true |

---

### Semantic Relationships

#### CONTAINED_IN, SIMILAR_TO, ALTERNATIVE_TO

No additional properties beyond mandatory fields.

---

### Dataset and Experimentation

#### EVALUATED_ON, USES_DATASET

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `metric` | string | ✗ | Evaluation metric (accuracy, F1, etc.). | "accuracy" |
| `score` | float | ✗ | Evaluation score. | 0.95 |

#### PRODUCED_BY

No additional properties.

---

### Metadata

#### EXTRACTED_FROM

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `chunk_index` | integer | ✗ | Which text chunk (if chunked). | 0 |

#### HAS_CHUNK

No additional properties beyond mandatory fields.

---

### Resolution

#### SAME_AS

Direction: `(Canonical)-[:SAME_AS]->(source entity)`. Carries the mandatory relationship fields with resolution semantics (same as the Canonical node), plus:

| Property | Type | Required | Description | Example |
|---|---|---|---|---|
| `confidence` | float | ✓ | Decision confidence (weakest supporting pair score). | 0.94 |
| `decision_action` | string | ✓ | "MERGE" or "TENTATIVE" (NONE decisions produce no edge). | "TENTATIVE" |
| `decided_at` | integer | ✓ | Unix timestamp of the resolution decision write. | 1784332800 |

---

## Uniqueness Constraints (indexes.cypher)

```cypher
CREATE CONSTRAINT unique_entity_id IF NOT EXISTS
  FOR (n:Entity) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_document_id IF NOT EXISTS
  FOR (n:Document) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_person_id IF NOT EXISTS
  FOR (n:Person) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_technology_id IF NOT EXISTS
  FOR (n:Technology) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_organization_id IF NOT EXISTS
  FOR (n:Organization) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT unique_canonical_id IF NOT EXISTS
  FOR (n:Canonical) REQUIRE n.id IS UNIQUE;
```

`unique_canonical_id` is separate from `unique_entity_id` because Canonical nodes deliberately do not carry the `:Entity` label (conceptual.md, Canonical section). `Chunk` needs no constraint of its own — it carries `:Entity` (conceptual.md, Chunk section) and `unique_entity_id` already covers it.

---

## Full-Text and Vector Indexes (indexes.cypher)

`graph/schema/indexes.cypher` did not exist as a real file before Step 9.5 — this section was documentation-only and nothing applied it. It now exists; this section matches it exactly. Two corrections made while materializing it, both flagged rather than carried over silently:

1. `document_fulltext` was scoped to `:Document`, which is abstract and never instantiated (physical.md says so explicitly, and this exact mistake was already caught once this session in a milestone-query context) — rescoped to `:Paper|Markdown`, the concrete labels.
2. The single `embedding` vector index is now **three** indexes, one per label/property pair, since `Chunk.embedding` (passage-level) and `Entity`/`Canonical.name_embedding` (short name-level) are different retrieval use cases that must not share a search space — see the `name_embedding` property notes above for why. Renamed accordingly: `entity_name_embedding`, `canonical_name_embedding`, `chunk_embedding`.

```cypher
CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
  FOR (n:Paper|Markdown) ON EACH [n.title, n.description];

CREATE FULLTEXT INDEX technology_fulltext IF NOT EXISTS
  FOR (n:Technology) ON EACH [n.name, n.description, n.aliases];

CREATE FULLTEXT INDEX person_fulltext IF NOT EXISTS
  FOR (n:Person) ON EACH [n.full_name];

CREATE VECTOR INDEX entity_name_embedding IF NOT EXISTS
  FOR (n:Entity) ON (n.name_embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_metric`: 'cosine'}};

CREATE VECTOR INDEX canonical_name_embedding IF NOT EXISTS
  FOR (n:Canonical) ON (n.name_embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_metric`: 'cosine'}};

CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
  FOR (n:Chunk) ON (n.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_metric`: 'cosine'}};
```

All three vector indexes store `all-MiniLM-L6-v2` embeddings (dimension 384, cosine similarity — the metric this model is trained against, and the same metric `resolution/matchers/embedding_matcher.py` already uses via L2-normalized dot product). Created before population, per the Step 9.5 STEP 1 decision — Neo4j vector indexes are a schema declaration, not a data operation; they populate automatically as the property gets set on matching nodes, in either order.

---

## Data Type Reference

| Type | Neo4j Equivalent | Notes |
|---|---|---|
| `string` | STRING | UTF-8 text |
| `integer` | INTEGER | 64-bit signed int |
| `float` | FLOAT | IEEE 754 double |
| `boolean` | BOOLEAN | true/false |
| `list[string]` | LIST OF STRING | Array of strings |
| `list[integer]` | LIST OF INTEGER | Array of integers |

---

## Example Records

### Person Node

```json
{
  "id": "person_alan_turing",
  "full_name": "Alan M. Turing",
  "email": "alan.turing@manchester.ac.uk",
  "orcid": "0000-0000-0000-0000",
  "homepage": "https://en.wikipedia.org/wiki/Alan_Turing",
  "birth_year": 1912,
  "confidence": 1.0,
  "extraction_source": "paper:Turing1936",
  "extraction_method": "manual"
}
```

### Paper Node

```json
{
  "id": "doc_arxiv_1706.03762",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani, A.", "Shazeer, N.", "Parmar, N.", "Uszkoreit, J.", "Jones, L.", "Gomez, A.N.", "Kaiser, Ł.", "Polosukhin, I."],
  "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
  "venue": "NeurIPS",
  "publication_year": 2017,
  "arxiv_id": "1706.03762",
  "doi": "10.5555/3295222.3295349",
  "source_url": "https://arxiv.org/pdf/1706.03762.pdf",
  "ingestion_timestamp": 1719331200,
  "file_hash": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ae8c7e25ad1065bfe2ac37db8c34",
  "page_count": 15,
  "language": "en",
  "content_type": "application/pdf",
  "confidence": 1.0,
  "extraction_source": "pdf:manual_upload",
  "extraction_method": "pdfplumber"
}
```

### Technology Node

```json
{
  "id": "tech_pytorch",
  "name": "PyTorch",
  "aliases": ["torch", "pytorch-lib"],
  "description": "An open source machine learning framework that accelerates the path from research prototyping to production deployment.",
  "category": "framework",
  "version_latest": "2.1.0",
  "website": "https://pytorch.org",
  "github_url": "https://github.com/pytorch/pytorch",
  "license": "BSD-3-Clause",
  "supported_languages": ["Python", "C++"],
  "confidence": 0.95,
  "extraction_source": "paper:Paszke2019",
  "extraction_method": "spacy:en_core_web_md"
}
```

### AUTHORED_BY Relationship

```json
{
  "role": "lead_author",
  "confidence": 1.0,
  "extraction_source": "paper:Vaswani2017",
  "extraction_method": "pdf_metadata"
}
```

---

**Document Version:** 1.3  
**Last Updated:** 2026-07-22  
**Status:** Complete for MVP + resolution layer (Canonical, SAME_AS) + Step 7 relationship extraction. Step 9.5 (ingestion persistence backfill) schema added: `Chunk` properties, `HAS_CHUNK`, `name_embedding` on Entity/Canonical, `indexes.cypher` materialized as a real file — all schema-only, no Chunk nodes or embeddings exist yet. Code entity properties (Phase 3) will expand once AST parsing is implemented.