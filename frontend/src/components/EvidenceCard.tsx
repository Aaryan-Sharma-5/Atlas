import type { EvidenceOut } from "../types/api";

interface EvidenceCardProps {
  evidence: EvidenceOut;
}

// api/schemas.py's QueryResponse.evidence is a SINGLE object, not a list — confirmed live against /api/v1/query in Step 14C Step 0 (both "What is ACL?" and "How do I install rdflib?" each returned exactly one evidence object, never an array). This component renders that one object, handling all three `shape` values it can carry rather than assuming chunk_content is always present.
export default function EvidenceCard({ evidence }: EvidenceCardProps) {
  if (evidence.chunk_content === null) {
    return (
      <div className="evidence-card evidence-card-empty">
        <p>No linked source passage for this answer.</p>
      </div>
    );
  }

  return (
    <div className="evidence-card">
      {evidence.source_document_title && (
        <div className="evidence-source">{evidence.source_document_title}</div>
      )}
      <p className="evidence-content">{evidence.chunk_content}</p>
    </div>
  );
}
