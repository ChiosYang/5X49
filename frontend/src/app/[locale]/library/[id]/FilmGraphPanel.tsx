"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/routing";
import { useFilmGraph } from "@/hooks/useFilm";
import { graphNodeHref } from "@/lib/explore";
import type { GraphEdge } from "@/types/movie";


const VIEW_WIDTH = 640;
const VIEW_HEIGHT = 480;
const CENTER_X = VIEW_WIDTH / 2;
const CENTER_Y = VIEW_HEIGHT / 2;
const RADIUS_X = 182;
const RADIUS_Y = 154;

type NodePosition = {
  x: number;
  y: number;
  labelX: number;
  labelY: number;
  textAnchor: "start" | "middle" | "end";
};

const point = (index: number, count: number): NodePosition => {
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const x = CENTER_X + cos * RADIUS_X;
  const y = CENTER_Y + sin * RADIUS_Y;

  if (Math.abs(cos) <= 0.22) {
    return { x, y, labelX: 0, labelY: sin < 0 ? -15 : 20, textAnchor: "middle" };
  }
  return {
    x,
    y,
    labelX: cos > 0 ? 12 : -12,
    labelY: 4,
    textAnchor: cos > 0 ? "start" : "end",
  };
};

const shortLabel = (value: string) => {
  let units = 0;
  let cut = 0;
  for (const char of value) {
    units += /[\u3000-\u9fff\uf900-\ufaff]/.test(char) ? 1.7 : 1;
    if (units > 17) return `${value.slice(0, cut)}…`;
    cut += char.length;
  }
  return value;
};

export default function FilmGraphPanel({ filmId }: { filmId: string }) {
  const t = useTranslations("FilmGraph");
  const router = useRouter();
  const { data, error, isLoading } = useFilmGraph(filmId);
  const layout = useMemo(() => {
    if (!data) return new Map<string, NodePosition>();
    const related = data.nodes.filter((node) => node.id !== data.root.id);
    return new Map<string, NodePosition>([
      [data.root.id, { x: CENTER_X, y: CENTER_Y, labelX: 0, labelY: 32, textAnchor: "middle" }],
      ...related.map((node, index) => [node.id, point(index, related.length)] as const),
    ]);
  }, [data]);

  if (isLoading) {
    return <section className="border-b border-line-strong px-8 py-10 text-ink-subtle md:px-16" aria-live="polite">{t("loading")}</section>;
  }
  if (error) {
    return <section className="border-b border-line-strong px-8 py-10 text-danger md:px-16" role="status">{t("error")}</section>;
  }
  if (!data || data.edges.length === 0) {
    return (
      <section className="border-b border-line-strong px-8 py-10 md:px-16">
        <span className="type-label text-ink-subtle">{t("title")}</span>
        <p className="mt-4 text-ink-muted">{t("empty")}</p>
      </section>
    );
  }

  const nodeById = new Map(data.nodes.map((node) => [node.id, node]));
  const relationTarget = (edge: GraphEdge) => nodeById.get(
    edge.subject_id === filmId ? edge.object_id : edge.subject_id,
  );

  return (
    <section className="border-b border-line-strong px-8 py-10 md:px-16" aria-labelledby="film-graph-title">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <span className="type-label text-ink-subtle">{t("eyebrow")}</span>
          <h2 id="film-graph-title" className="type-section-title mt-2 text-ink">{t("title")}</h2>
        </div>
        <span className="type-meta text-ink-subtle">{t("factualPolicy")}</span>
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)]">
        <div className="min-w-0 overflow-hidden border border-line bg-surface">
          <svg viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`} className="block aspect-[4/3] w-full max-h-[38rem]" role="img" aria-label={t("diagramLabel")}>
            {data.edges.map((edge) => {
              const from = layout.get(edge.subject_id);
              const to = layout.get(edge.object_id);
              if (!from || !to) return null;
              return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="var(--color-line-strong)" strokeWidth="1" strokeOpacity="0.65" />;
            })}
            {data.nodes.map((node) => {
              const position = layout.get(node.id);
              if (!position) return null;
              const isRoot = node.id === data.root.id;
              const href = graphNodeHref(node, filmId);
              const label = `${node.display_label}${node.release_year ? `, ${node.release_year}` : ""}`;
              const nodeGraphic = (
                <g transform={`translate(${position.x} ${position.y})`}>
                  {isRoot && (
                    <circle
                      r={18}
                      fill="none"
                      stroke="var(--color-line-strong)"
                      strokeWidth={1}
                      strokeOpacity="0.6"
                    />
                  )}
                  <circle
                    r={isRoot ? 10 : node.entity_type === "film" ? 5.5 : 4.5}
                    fill={isRoot ? "var(--color-inverse)" : node.entity_type === "film" ? "var(--color-ink)" : "var(--color-surface-raised)"}
                    stroke={isRoot ? "var(--color-ink)" : node.entity_type === "concept" ? "var(--color-ink-subtle)" : "var(--color-ink-muted)"}
                    strokeWidth={isRoot ? 1.5 : 1.25}
                    className="transition-[stroke,stroke-width] duration-fast group-hover:stroke-ink group-focus-visible:stroke-ink group-focus-visible:stroke-[2.5]"
                  />
                  <text
                    x={position.labelX}
                    y={position.labelY}
                    textAnchor={position.textAnchor}
                    fill="var(--color-ink)"
                    fontSize={isRoot ? 12.5 : 11}
                    fontWeight={isRoot ? "700" : "600"}
                    paintOrder="stroke"
                    stroke="var(--color-surface)"
                    strokeWidth={isRoot ? 5 : 4}
                    strokeLinejoin="round"
                  >
                    {shortLabel(node.display_label)}
                  </text>
                  {!isRoot && node.release_year && (
                    <text
                      x={position.labelX}
                      y={position.labelY + 12}
                      textAnchor={position.textAnchor}
                      fill="var(--color-ink-subtle)"
                      fontSize="9.5"
                      paintOrder="stroke"
                      stroke="var(--color-surface)"
                      strokeWidth="3.5"
                      strokeLinejoin="round"
                    >
                      {node.release_year}
                    </text>
                  )}
                </g>
              );
              if (!href) {
                return <g key={node.id} role="group" aria-label={label}>{nodeGraphic}</g>;
              }
              return (
                <g
                  key={node.id}
                  role="link"
                  tabIndex={0}
                  aria-label={label}
                  className="group cursor-pointer focus:outline-none"
                  onClick={() => router.push(href)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      router.push(href);
                    }
                  }}
                >
                  {nodeGraphic}
                </g>
              );
            })}
          </svg>
        </div>

        <div className="min-w-0">
          <h3 className="type-label text-ink-subtle">{t("relations")}</h3>
          <ul className="mt-4 max-h-[42rem] divide-y divide-line overflow-y-auto border-y border-line">
            {data.edges.map((edge) => {
              const target = relationTarget(edge);
              if (!target) return null;
              const href = graphNodeHref(target, filmId);
              const content = (
                <>
                  <span className="type-badge block text-ink-subtle">{t(`relationsMap.${edge.relation}` as never)}</span>
                  <span className="mt-1 block break-words font-bold text-ink">{target.display_label}</span>
                  <span className="type-meta mt-1 block text-ink-subtle">
                    {t("source", { source: edge.source_kinds.join(" · ") || t("structured") })}
                    {edge.active_evidence_count > 0 ? ` · ${t("evidence", { count: edge.active_evidence_count })}` : ""}
                  </span>
                </>
              );
              return (
                <li key={edge.id} className="py-4">
                  {href ? (
                    <Link
                      href={href}
                      className="focus-ring block w-full min-w-0 text-left"
                      onKeyDown={(event) => {
                        if (event.key === " ") {
                          event.preventDefault();
                          router.push(href);
                        }
                      }}
                    >
                      {content}
                    </Link>
                  ) : (
                    <div className="w-full min-w-0 text-left">{content}</div>
                  )}
                </li>
              );
            })}
          </ul>
          {data.truncated && <p className="type-meta mt-4 text-warning">{t("truncated")}</p>}
        </div>
      </div>
    </section>
  );
}
