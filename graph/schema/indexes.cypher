// Full-text and vector indexes for the Atlas knowledge graph.
// Applied by graph/builders/neo4j_writer.py (Neo4jWriter.apply_constraints,
// same mechanism as constraints.cypher) before any write.
//
// This file did not exist before Step 9.5 (physical.md documented it in
// prose only). Corrections made while materializing it — see physical.md's
// "Full-Text and Vector Indexes" section for the first two; a third found
// only once this file was actually applied to a live Neo4j (embedding
// generation close-out): the config key is `vector.similarity_function`
// in Neo4j 5.16, not `vector.similarity_metric` as originally documented -
// that name was never tested against a real database until this point.

CREATE FULLTEXT INDEX document_fulltext IF NOT EXISTS
FOR (n:Paper|Markdown) ON EACH [n.title, n.description];

CREATE FULLTEXT INDEX technology_fulltext IF NOT EXISTS
FOR (n:Technology) ON EACH [n.name, n.description, n.aliases];

CREATE FULLTEXT INDEX person_fulltext IF NOT EXISTS
FOR (n:Person) ON EACH [n.full_name];

// Added Step 10D+ (retrieval eval, question 15): missing from the original three,
// not a deliberate scoping choice - Organization is the most common KnowledgeEntity
// label in this corpus (architecture.md §12.3), so its absence meant short
// Organization-labeled names/acronyms ("ACL", "RDF") returned zero keyword hits
// even when an exact-name entity existed. Same property set as technology_fulltext.
CREATE FULLTEXT INDEX organization_fulltext IF NOT EXISTS
FOR (n:Organization) ON EACH [n.name, n.description, n.aliases];

// Short name-similarity search (Person/Organization/Technology/... via :Entity,
// and Canonical separately since it doesn't carry :Entity). NOT the same
// property or index as chunk_embedding below - see physical.md.
CREATE VECTOR INDEX entity_name_embedding IF NOT EXISTS
FOR (n:Entity) ON (n.name_embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

CREATE VECTOR INDEX canonical_name_embedding IF NOT EXISTS
FOR (n:Canonical) ON (n.name_embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};

// Passage-level semantic search over Chunk text (Step 9.5). Created before
// any Chunk carries an embedding - vector indexes populate incrementally as
// the property is set, same as any other Neo4j index.
CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
FOR (n:Chunk) ON (n.embedding)
OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
