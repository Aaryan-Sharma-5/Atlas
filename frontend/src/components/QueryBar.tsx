import { useState } from "react";

interface QueryBarProps {
  onSubmit: (question: string) => void;
  disabled: boolean;
}

// Pulled from examples/expected_output/retrieval_eval_questions.json — questions already verified live against the API (Step 14A/14C) to produce a clean 200, not invented examples. Graph-routed questions (Q1/Q3/etc.) are deliberately excluded: /api/v1/query has no graph_seed_id param, so those would 422 as a first click.
const EXAMPLE_QUESTIONS = [
  "Find entities/canonicals whose name is closest to 'RDF library'.",
  "How does entity resolution merge duplicate entities?",
  "How do I install rdflib?",
  "What is ACL?",
];

export default function QueryBar({ onSubmit, disabled }: QueryBarProps) {
  const [question, setQuestion] = useState("");

  function submit(q: string) {
    const trimmed = q.trim();
    if (trimmed.length === 0) return;
    onSubmit(trimmed);
  }

  return (
    <div className="query-bar">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(question);
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask a question about the corpus..."
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || question.trim().length === 0}>
          {disabled ? "Asking..." : "Ask"}
        </button>
      </form>
      <div className="example-questions">
        {EXAMPLE_QUESTIONS.map((q) => (
          <button
            key={q}
            type="button"
            className="example-question"
            disabled={disabled}
            onClick={() => {
              setQuestion(q);
              submit(q);
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
