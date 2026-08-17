import { API_ORIGIN } from "./client";

// Layer 1: wakes a sleeping Render process (api/main.py's "/", the same path render.yaml's healthCheckPath already targets).
export async function ping(): Promise<void> {
  const res = await fetch(`${API_ORIGIN}/`);
  if (!res.ok) throw new Error(`health check failed: ${res.status}`);
}

// Layer 2: loads the ONNX embedding model into memory ahead of the user's first real query 
export async function warmup(): Promise<void> {
  const res = await fetch(`${API_ORIGIN}/warmup`);
  if (!res.ok) throw new Error(`warmup failed: ${res.status}`);
}
