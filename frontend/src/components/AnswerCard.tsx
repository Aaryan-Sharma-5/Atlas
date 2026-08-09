import type { QueryResponse } from "../types/api";
import ConfidenceBadge from "./ConfidenceBadge";

interface AnswerCardProps {
  response: QueryResponse;
}

// routing_decision's real values (planner/query_classifier.py): "graph", "vector_name", "vector_passage", "keyword", "hybrid" — vector_name/vector_passage both collapse to one VECTOR badge, per the plan's GRAPH/VECTOR/KEYWORD/HYBRID display.
function routingBadgeLabel(routingDecision: string): string {
  if (routingDecision.startsWith("vector")) return "VECTOR";
  return routingDecision.toUpperCase();
}

export default function AnswerCard({ response }: AnswerCardProps) {
  return (
    <div className="answer-card">
      <div className="answer-card-meta">
        <span className="routing-badge">{routingBadgeLabel(response.routing_decision)}</span>
        <ConfidenceBadge
          confidenceLabel={response.confidence_label}
          confidenceScore={response.confidence_score}
        />
      </div>
      <p className="answer-text">{response.answer_display_text}</p>
    </div>
  );
}
