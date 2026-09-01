"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";

import { Link, useRouter } from "@/i18n/routing";
import { useFilmGraph } from "@/hooks/useFilm";
import { graphNodeHref } from "@/lib/explore";
import type { GraphEdge } from "@/types/movie";


const point = (index: number, count: number) => {
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(count, 1);
  return { x: 50 + Math.cos(angle) * 39, y: 50 + Math.sin(angle) * 39 };
};

const shortLabel = (value: string) => value.length > 16 ? `${value.slice(0, 15)}…` : value;

export default function FilmGraphPanel({ filmId }: { filmId: string }) {
  const t = useTranslations("FilmGraph");
  const router = useRouter();
  const { data, error, isLoading } = useFilmGraph(filmId);
  const layout = useMemo(() => {
    if (!data) return new Map<string, { x: number; y: number }>();
    const related = data.nodes.filter((node) => node.id !== data.root.id);
    return new Map([
      [data.root.id, { x: 50, y: 50 }],
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
          <svg viewBox="0 0 100 100" className="block aspect-square w-full max-h-[42rem]" role="img" aria-label={t("diagramLabel")}>
            {data.edges.map((edge) => {
              const from = layout.get(edge.subject_id);
              const to = layout.get(edge.object_id);
              if (!from || !to) return null;
              return <line key={edge.id} x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke="var(--color-line-strong)" strokeWidth="0.35" />;
            })}
            {data.nodes.map((node) => {
              const position = layout.get(node.id);
              if (!position) return null;
              const isRoot = node.id === data.root.id;
              const href = graphNodeHref(node, filmId);
              const label = `${node.display_label}${node.release_year ? `, ${node.release_year}` : ""}`;
              const nodeGraphic = (
                <g transform={`translate(${position.x} ${position.y})`}>
                  <circle
                    r={isRoot ? 8.5 : 5.6}
                    fill={isRoot ? "var(--color-inverse)" : "var(--color-surface-raised)"}
                    stroke={node.entity_type === "concept" ? "var(--color-ink-subtle)" : "var(--color-line-strong)"}
                    strokeWidth={isRoot ? 0.6 : 0.4}
                  />
                  <text
                    y={isRoot ? 0.5 : 0.3}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill={isRoot ? "var(--color-inverse-ink)" : "var(--color-ink)"}
                    fontSize={isRoot ? 2.7 : 1.9}
                    fontWeight="700"
                  >
                    {shortLabel(node.display_label)}
                  </text>
                  {!isRoot && node.release_year && (
                    <text y="3" textAnchor="middle" fill="var(--color-ink-subtle)" fontSize="1.4">{node.release_year}</text>
                  )}
                </g>
              );
              if (!href) {
                return <g key={node.id} role="group" aria-label={label}>{nodeGraphic}</g>;
              }
              return (
                <Link
                  key={node.id}
                  href={href}
                  aria-label={label}
                  className="cursor-pointer focus:outline-none focus:[&>g>circle]:stroke-ink"
                  onKeyDown={(event) => {
                    if (event.key === " ") {
                      event.preventDefault();
                      router.push(href);
                    }
                  }}
                >
                  {nodeGraphic}
                </Link>
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
