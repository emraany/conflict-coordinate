import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

import { api, ApiError } from "../api/client";
import { colors, fonts, space } from "../styles/tokens";
import type { CrisisGraph } from "../types";

const COMMUNITY_PALETTE = [
  "#8a9070",
  "#a64a3a",
  "#c8a96a",
  "#6b727c",
  "#a8a294",
  "#525862",
  "#4a523c",
  "#7c7a6e",
];

interface Props {
  slug: string;
  defaultOpen?: boolean;
}

interface RFGNode {
  id: string;
  label: string;
  mentions: number;
  community: number;
  centrality: number;
}

interface RFGLink {
  source: string;
  target: string;
  weight: number;
}

export function RelationshipsSection({ slug, defaultOpen = false }: Props) {
  const [graph, setGraph] = useState<CrisisGraph | null>(null);
  const [open, setOpen] = useState(defaultOpen);
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setGraph(null);
    api
      .getCrisisGraph(slug)
      .then((g) => { if (!cancelled) setGraph(g); })
      .catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return;
      });
    return () => { cancelled = true; };
  }, [slug]);

  useEffect(() => {
    if (!open) return;
    const el = containerRef.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [open, graph]);

  const data = useMemo(() => {
    if (!graph) return { nodes: [] as RFGNode[], links: [] as RFGLink[] };
    return {
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ ...e })),
    };
  }, [graph]);

  if (!graph || graph.nodes.length === 0) return null;

  const maxMentions = Math.max(...graph.nodes.map((n) => n.mentions));

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: space.md,
          marginBottom: space.sm,
          flexWrap: "wrap",
        }}
      >
        <button
          onClick={() => setOpen((v) => !v)}
          style={{
            background: "none",
            border: `1px solid ${colors.oliveDim}`,
            padding: `${space.xs}px ${space.sm}px`,
            cursor: "pointer",
            fontFamily: fonts.mono,
            fontSize: 11,
            color: colors.oliveLight,
            letterSpacing: "0.16em",
          }}
        >
          [ {open ? "HIDE" : "SHOW"} NETWORK VIEW ]
        </button>
        <span
          className="label"
          style={{ fontSize: 10, color: colors.textMuted, fontFamily: fonts.mono }}
        >
          {graph.nodes.length} groups · {graph.edges.length} links · {graph.communities.length} cluster{graph.communities.length === 1 ? "" : "s"}
        </span>
      </div>

      {open && (
        <div
          ref={containerRef}
          style={{
            border: `1px solid ${colors.rule}`,
            background: colors.bgSunken,
            height: 360,
            position: "relative",
            overflow: "hidden",
          }}
        >
          {width > 0 && (
            <ForceGraph2D
              graphData={data}
              width={width}
              height={360}
              backgroundColor={colors.bgSunken}
              nodeRelSize={4}
              nodeVal={(n) => 1 + 6 * ((n as RFGNode).mentions / maxMentions)}
              nodeColor={(n) =>
                COMMUNITY_PALETTE[
                  (n as RFGNode).community % COMMUNITY_PALETTE.length
                ]
              }
              nodeLabel={(n) => {
                const nn = n as RFGNode;
                return `${nn.label} — ${nn.mentions} mention${nn.mentions === 1 ? "" : "s"}`;
              }}
              linkColor={() => colors.rule}
              linkWidth={(l) => Math.min(3, Math.log1p((l as RFGLink).weight))}
              cooldownTicks={120}
              nodeCanvasObjectMode={() => "after"}
              nodeCanvasObject={(node, ctx, globalScale) => {
                const n = node as RFGNode & { x?: number; y?: number };
                if (n.x === undefined || n.y === undefined) return;
                if (n.mentions / maxMentions < 0.15) return;
                const fontSize = Math.max(8, 11 / globalScale);
                ctx.font = `${fontSize}px ${fonts.mono}`;
                ctx.textAlign = "center";
                ctx.textBaseline = "top";
                ctx.fillStyle = colors.text;
                const r = 1 + 6 * (n.mentions / maxMentions);
                ctx.fillText(n.label.slice(0, 24), n.x, n.y + r + 2);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}
