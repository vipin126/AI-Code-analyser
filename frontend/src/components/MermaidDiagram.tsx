"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { DependencyGraphData } from "@/types";

interface MermaidDiagramProps {
  graphData?: DependencyGraphData;
  rawChart?: string;
}

export default function MermaidDiagram({ graphData, rawChart }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Generate Mermaid definition from AST Graph Data if rawChart is not supplied
  const chartDefinition =
    rawChart ||
    (graphData
      ? generateMermaidFromGraph(graphData)
      : "graph TD\n  Start[No Graph Available]");

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      themeVariables: {
        darkMode: true,
        background: "#030712",
        primaryColor: "#2563eb",
        primaryTextColor: "#ffffff",
        primaryBorderColor: "#3b82f6",
        lineColor: "#64748b",
        secondaryColor: "#1e293b",
        tertiaryColor: "#0f172a",
      },
    });

    let isMounted = true;
    const uniqueId = `mermaid-${Math.random().toString(36).substring(2, 9)}`;

    async function renderChart() {
      try {
        setError(null);
        const { svg } = await mermaid.render(uniqueId, chartDefinition);
        if (isMounted) {
          setSvgContent(svg);
        }
      } catch (err) {
        if (isMounted) {
          console.error("Mermaid render failure:", err);
          setError("Failed to render diagram. Code graph may contain cyclical or invalid characters.");
        }
      }
    }

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [chartDefinition]);

  return (
    <div className="w-full rounded-xl border border-gray-800 bg-gray-950/70 p-4">
      {error ? (
        <div className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-xs text-red-400">
          <p className="font-semibold mb-1">Architecture Rendering Notice:</p>
          <p>{error}</p>
          <pre className="mt-3 overflow-x-auto rounded bg-gray-900/60 p-2 text-[10px] text-gray-400">
            {chartDefinition}
          </pre>
        </div>
      ) : (
        <div
          ref={containerRef}
          className="flex justify-center overflow-x-auto min-h-[350px] items-center [&_svg]:max-w-full [&_svg]:h-auto"
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      )}
    </div>
  );
}

function sanitizeId(str: string): string {
  return str.replace(/[^a-zA-Z0-9_]/g, "_");
}

function generateMermaidFromGraph(graph: DependencyGraphData): string {
  const lines: string[] = ["graph LR"];

  // Limit to 50 nodes and 70 edges to prevent rendering bottlenecks on huge repos
  const nodes = graph.nodes.slice(0, 50);
  const edges = graph.edges.slice(0, 70);

  if (nodes.length === 0) {
    return "graph TD\n  Empty[No AST nodes detected]";
  }

  // Node styling by type
  nodes.forEach((node) => {
    const sId = sanitizeId(node.id);
    const label = `${node.name} (${node.type})`;
    lines.push(`  ${sId}["${label}"]`);
  });

  // Edges
  edges.forEach((edge) => {
    const sSource = sanitizeId(edge.source);
    const sTarget = sanitizeId(edge.target);
    lines.push(`  ${sSource} -->|${edge.relationship}| ${sTarget}`);
  });

  return lines.join("\n");
}
