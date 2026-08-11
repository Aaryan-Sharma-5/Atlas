import { useEffect, useState } from "react";
import { fetchEntityDetail } from "../api/entities";
import { ApiError } from "../api/client";
import type { EntityDetailResponse } from "../types/api";

interface EntityPanelProps {
  entityId: string;
  onClose: () => void;
}

type Result =
  | { key: string; kind: "ready"; data: EntityDetailResponse }
  | { key: string; kind: "error"; message: string };

function isDisplayableProperty(key: string, value: unknown): value is string | number | boolean | unknown[] {
  if (value === null || value === undefined || value === "") return false;
  if (key.toLowerCase().includes("embedding")) return false;
  return true;
}

function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatValue(key: string, value: string | number | boolean | unknown[]): string {
  if (key === "created_at" && typeof value === "number") {
    return new Date(value * 1000).toLocaleDateString();
  }
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function EntityPanelContent({ data }: { data: EntityDetailResponse }) {
  const displayProperties = Object.entries(data.properties).filter(([k, v]) => isDisplayableProperty(k, v));

  return (
    <>
      <div className="entity-panel-header">
        {data.node_type && <span className="routing-badge">{data.node_type.toUpperCase()}</span>}
        {data.is_canonical && <span className="entity-panel-canonical-tag">Canonical</span>}
      </div>
      <h2 className="entity-panel-name">{data.name ?? data.id}</h2>
      <div className="entity-panel-confidence">{(data.confidence * 100).toFixed(0)}% confidence</div>

      <div className="entity-panel-provenance">
        Source: {data.extraction_source} · Method: {data.extraction_method}
      </div>

      {data.is_canonical && data.aliases.length > 0 && (
        <div className="entity-panel-section">
          <h3>Aliases ({data.aliases.length})</h3>
          <ul className="entity-panel-aliases">
            {data.aliases.map((alias) => (
              <li key={alias.id}>
                <span>{alias.name ?? alias.id}</span>
                {alias.decision_action && (
                  <span className="entity-panel-alias-tag">{alias.decision_action}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {displayProperties.length > 0 && (
        <div className="entity-panel-section">
          <h3>Properties</h3>
          <dl className="entity-panel-properties">
            {displayProperties.map(([key, value]) => (
              <div key={key} className="entity-panel-property-row">
                <dt>{humanizeKey(key)}</dt>
                <dd>{formatValue(key, value as string | number | boolean | unknown[])}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </>
  );
}

export default function EntityPanel({ entityId, onClose }: EntityPanelProps) {
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEntityDetail(entityId)
      .then((data) => {
        if (!cancelled) setResult({ key: entityId, kind: "ready", data });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({
            key: entityId,
            kind: "error",
            // Covers the 404 case (a clicked node id somehow not resolving) with the same plain-error treatment /query and /entities/{id}/graph already use — shouldn't happen for a node GraphView itself rendered, but not assumed.
            message: err instanceof ApiError ? err.message : "Could not load entity details.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const loading = !result || result.key !== entityId;

  return (
    <div className="entity-panel-backdrop" onClick={onClose}>
      <div className="entity-panel" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="entity-panel-close" onClick={onClose} aria-label="Close">
          ×
        </button>
        {loading && <p className="status-loading">Loading entity...</p>}
        {!loading && result.kind === "error" && <p className="status-error">{result.message}</p>}
        {!loading && result.kind === "ready" && <EntityPanelContent data={result.data} />}
      </div>
    </div>
  );
}
