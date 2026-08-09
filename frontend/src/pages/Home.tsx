import { useState } from "react";
import { runQuery } from "../api/query";
import { ApiError } from "../api/client";
import type { QueryResponse } from "../types/api";
import QueryBar from "../components/QueryBar";
import AnswerCard from "../components/AnswerCard";
import EvidenceCard from "../components/EvidenceCard";

type Status = "idle" | "loading" | "error";

export default function Home() {
  const [status, setStatus] = useState<Status>("idle");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleAsk(question: string) {
    setStatus("loading");
    setErrorMessage(null);
    try {
      const result = await runQuery(question);
      setResponse(result);
      setStatus("idle");
    } catch (err) {
      // Reuses the backend's existing clean 422 (e.g. graph routing without a graph_seed_id) / 404 (no results) patterns — their `detail` string surfaces directly, no new error taxonomy invented on the frontend.
      const message = err instanceof ApiError ? err.message : "Something went wrong.";
      setErrorMessage(message);
      setStatus("error");
    }
  }

  return (
    <main className="home">
      <h1>Atlas</h1>
      <QueryBar onSubmit={handleAsk} disabled={status === "loading"} />

      {status === "loading" && <p className="status-loading">Asking...</p>}
      {status === "error" && errorMessage && <p className="status-error">{errorMessage}</p>}

      {response && status !== "loading" && (
        <div className="results">
          <AnswerCard response={response} />
          <EvidenceCard evidence={response.evidence} />
        </div>
      )}
    </main>
  );
}
