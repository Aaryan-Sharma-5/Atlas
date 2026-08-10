import { useEffect, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import type { Core, ElementDefinition, StylesheetJson } from "cytoscape";
import { fetchEntityGraph } from "../api/entities";
import { ApiError } from "../api/client";
import type { EntityGraphResponse } from "../types/api";

interface GraphViewProps {
  entityId: string;
}

const LIMIT_STEP = 100;
const MAX_LIMIT = 500;

type Result =
  | { key: string; kind: "ready"; data: EntityGraphResponse }
  | { key: string; kind: "error"; message: string };

const STYLESHEET: StylesheetJson = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "font-size": 9,
      color: "#08060d",
      "text-valign": "bottom",
      "text-margin-y": 4,
      "background-color": "#c9c3d6",
      width: 22,
      height: 22,
    },
  },
  { selector: "node.canonical", style: { "background-color": "#aa3bff" } },
  {
    selector: "node.seed",
    style: { "border-width": 3, "border-color": "#08060d", width: 30, height: 30 },
  },
  {
    selector: "edge",
    style: {
      label: "data(label)",
      "font-size": 7,
      color: "#6b6375",
      "curve-style": "bezier",
      "target-arrow-shape": "triangle",
      "arrow-scale": 0.7,
      width: 1,
      "line-color": "#e5e4e7",
      "target-arrow-color": "#e5e4e7",
    },
  },
];

function toElements(data: EntityGraphResponse, seedId: string): ElementDefinition[] {
  const nodes: ElementDefinition[] = data.nodes.map((n) => ({
    data: { id: n.id, label: n.label },
    classes: [n.id === seedId ? "seed" : null, n.target_resolution === "canonical" ? "canonical" : null]
      .filter(Boolean)
      .join(" "),
  }));
  const edges: ElementDefinition[] = data.edges.map((e, i) => ({
    data: { id: `e${i}`, source: e.source, target: e.target, label: e.relationship_type },
  }));
  return [...nodes, ...edges];
}

export default function GraphView({ entityId }: GraphViewProps) {
  const [limit, setLimit] = useState(LIMIT_STEP);
  const [result, setResult] = useState<Result | null>(null);
  const requestKey = `${entityId}:${limit}`;
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchEntityGraph(entityId, limit)
      .then((data) => {
        if (!cancelled) setResult({ key: requestKey, kind: "ready", data });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({
            key: requestKey,
            kind: "error",
            message: err instanceof ApiError ? err.message : "Could not load the graph.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, limit, requestKey]);

  // Loading is "current result is stale or missing" — derived at render time rather than set synchronously in the effect, per react-hooks/set-state-in-effect.
  if (!result || result.key !== requestKey) {
    return <p className="status-loading">Loading graph...</p>;
  }
  if (result.kind === "error") return <p className="status-error">{result.message}</p>;
  const { data } = result;

  return (
    <div className="graph-view">
      <div className="graph-view-header">
        <span>
          {data.truncated
            ? `Showing ${data.nodes.length} of many connections`
            : `Showing all ${data.nodes.length} connections`}
        </span>
        {data.truncated && (
          <button
            type="button"
            className="load-more-button"
            onClick={() => setLimit((l) => Math.min(l + LIMIT_STEP, MAX_LIMIT))}
            disabled={limit >= MAX_LIMIT}
          >
            Load more
          </button>
        )}
      </div>
      <CytoscapeComponent
        key={`${entityId}-${limit}`}
        elements={toElements(data, entityId)}
        style={{ width: "100%", height: "420px" }}
        layout={{ name: "cose", animate: false, fit: true, padding: 30 }}
        stylesheet={STYLESHEET}
        className="graph-view-canvas"
        cy={(cy) => {
          cyRef.current = cy;
          requestAnimationFrame(() => {
            cy.resize();
            cy.fit(undefined, 30);
          });
        }}
      />
    </div>
  );
}
