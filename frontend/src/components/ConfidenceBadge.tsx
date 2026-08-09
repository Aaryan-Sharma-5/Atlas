interface ConfidenceBadgeProps {
  confidenceLabel: string;
  confidenceScore: number;
}

// Renders confidence_label (human text) — never confidence_method, the raw internal tag (e.g. "cosine_similarity_name") verified present alongside it in the real /api/v1/query response but not meant for display (api/schemas.py's own comment).
export default function ConfidenceBadge({ confidenceLabel, confidenceScore }: ConfidenceBadgeProps) {
  return (
    <span className="confidence-badge">
      {confidenceLabel} · {(confidenceScore * 100).toFixed(0)}%
    </span>
  );
}
