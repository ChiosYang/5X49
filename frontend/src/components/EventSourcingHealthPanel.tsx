"use client";

import { CheckCircle2, Database, RefreshCw, TriangleAlert } from "lucide-react";
import useSWR from "swr";

import { Button } from "@/components/ui/Button";
import { InlineFeedback, Spinner } from "@/components/ui/Feedback";
import { API } from "@/lib/api";
import type { EventRecord, LibraryFilmSummary, WorkflowRunView } from "@/types/movie";

const fetcher = async <T,>(url: string): Promise<T> => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Health query failed: ${response.status}`);
  return response.json();
};

export default function EventSourcingHealthPanel() {
  const films = useSWR<LibraryFilmSummary[]>(API.libraryFilms(), fetcher);
  const workflows = useSWR<WorkflowRunView[]>(API.workflows(), fetcher);
  const events = useSWR<EventRecord[]>(API.activityEvents({ limit: 100 }), fetcher);
  const loading = films.isLoading || workflows.isLoading || events.isLoading;
  const error = films.error || workflows.error || events.error;
  const invalidFilms = (films.data || []).filter((film) => !film.id || !film.primary_item?.id || film.primary_item.film_id !== film.id);
  const activeWorkflows = (workflows.data || []).filter((workflow) => ["queued", "running"].includes(workflow.status));
  const failedWorkflows = (workflows.data || []).filter((workflow) => workflow.status === "failed");
  const snapshots = (events.data || []).filter((event) => event.operation_snapshot_id).length;
  const healthy = !error && invalidFilms.length === 0;

  const refresh = async () => Promise.all([films.mutate(), workflows.mutate(), events.mutate()]);

  return (
    <section className="space-y-5 border-y border-line py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="inline-flex h-9 w-9 items-center justify-center border border-line text-ink-muted">
            <Database className="h-4 w-4" />
          </span>
          <div>
            <p className="type-label text-ink-subtle">Canonical runtime health</p>
            <p className="mt-1 type-body text-ink-muted">Film/LibraryItem integrity, recoverable snapshots and durable workflows.</p>
          </div>
        </div>
        <Button onClick={refresh} disabled={loading} busy={loading}>
          <RefreshCw className="h-4 w-4" /> Refresh
        </Button>
      </div>

      {error && <InlineFeedback tone="error">Canonical health data could not be loaded.</InlineFeedback>}
      {loading && !error ? <Spinner className="h-5 w-5" /> : null}
      {!loading && !error && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Metric label="Films" value={films.data?.length || 0} />
            <Metric label="Integrity issues" value={invalidFilms.length} warning={invalidFilms.length > 0} />
            <Metric label="Active workflows" value={activeWorkflows.length} />
            <Metric label="Failed workflows" value={failedWorkflows.length} warning={failedWorkflows.length > 0} />
            <Metric label="Recoverable events" value={snapshots} />
          </div>
          <p className={`flex items-center gap-2 type-body ${healthy ? "text-success" : "text-warning"}`}>
            {healthy ? <CheckCircle2 className="h-4 w-4" /> : <TriangleAlert className="h-4 w-4" />}
            {healthy ? "Canonical resource links are consistent in the current page of data." : "Canonical resource links need attention."}
          </p>
        </>
      )}
    </section>
  );
}

function Metric({ label, value, warning = false }: { label: string; value: number; warning?: boolean }) {
  return (
    <div className="border border-line p-4">
      <p className="type-meta text-ink-subtle">{label}</p>
      <p className={`mt-2 text-2xl font-black ${warning ? "text-warning" : "text-ink"}`}>{value}</p>
    </div>
  );
}
