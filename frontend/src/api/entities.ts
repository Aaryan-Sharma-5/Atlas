import { get } from "./client";
import type { EntityGraphResponse } from "../types/api";

export function fetchEntityGraph(entityId: string, limit: number): Promise<EntityGraphResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return get<EntityGraphResponse>(`/entities/${encodeURIComponent(entityId)}/graph?${params}`);
}
