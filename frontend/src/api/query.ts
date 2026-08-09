import { post } from "./client";
import type { QueryRequest, QueryResponse } from "../types/api";

export function runQuery(question: string, topK = 5): Promise<QueryResponse> {
  const body: QueryRequest = { question, top_k: topK };
  return post<QueryResponse>("/query", body);
}
