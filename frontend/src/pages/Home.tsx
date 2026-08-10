import { useState } from "react";
import { runQuery } from "../api/query";
import { ApiError } from "../api/client";
import type { QueryResponse } from "../types/api";
import QueryBar from "../components/QueryBar";
import AnswerCard from "../components/AnswerCard";
import EvidenceCard from "../components/EvidenceCard";
import GraphView from "../components/GraphView";

type Status = "idle" | "loading" | "error";

interface DisplayError {
  tone: "caveat" | "error";
  message: string;
}

function describeQueryError(err: unknown): DisplayError {
  if (err instanceof ApiError && err.status === 422 && err.message.includes("graph_seed_id")) {
    return {
      tone: "caveat",
      message:
        "This question needs a specific entity to start from — free-text entity linking for graph queries isn't built yet.",
    };
  }
  return {
    tone: "error",
    message: err instanceof ApiError ? err.message : "Something went wrong.",
  };
}

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);
  const [exploring, setExploring] = useState(false);

  async function handleAsk(question: string) {
    setStatus("loading");
    setError(null);
    setExploring(false);
    try {
      const result = await runQuery(question);
      setResponse(result);
      setStatus("idle");
    } catch (err) {
      setError(describeQueryError(err));
      setStatus("error");
    }
  }

  return (
    <main className="home">
      <h1>Atlas</h1>
      <QueryBar onSubmit={handleAsk} disabled={status === "loading"} />

      {status === "loading" && <p className="status-loading">Asking...</p>}
      {status === "error" && error && (
        <p className={error.tone === "caveat" ? "status-caveat" : "status-error"}>
          {error.message}
        </p>
      )}

      {response && status !== "loading" && (
        <div className="results">
          <AnswerCard response={response} />
          <EvidenceCard evidence={response.evidence} />

          {!exploring && (
            <button
              type="button"
              className="explore-graph-button"
              onClick={() => setExploring(true)}
            >
              Explore graph
            </button>
          )}
          {exploring && <GraphView entityId={response.answer_entity_id} />}
        </div>
      )}
    </main>
  );
}
