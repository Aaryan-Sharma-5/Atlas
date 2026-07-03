// Uniqueness constraints for the Atlas knowledge graph.
// Applied by graph/builders/neo4j_writer.py before any write.
//
// Every node carries the :Entity label (plus base type + specific type),
// so this single constraint guarantees id uniqueness graph-wide and
// backs it with an index for MATCH-by-id lookups.

CREATE CONSTRAINT unique_entity_id IF NOT EXISTS
FOR (n:Entity) REQUIRE n.id IS UNIQUE;
