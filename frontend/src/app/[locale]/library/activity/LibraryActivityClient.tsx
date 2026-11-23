"use client";

import { ChevronDown, Clock, Filter, RotateCcw } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import useSWR, { mutate } from "swr";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { InlineFeedback, Spinner, StateMessage } from "@/components/ui/Feedback";
import { FormField, Select, TextInput } from "@/components/ui/FormControls";
import { useOperationPreview, useRestoreOperation } from "@/hooks/useFilm";
import { Link } from "@/i18n/routing";
import { API } from "@/lib/api";
import type { EventRecord } from "@/types/movie";

const aggregateTypes = ["film", "library_item", "viewing", "assertion", "analysis_run", "job"];

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function eventLabel(value: string) {
  return value.replace(/([a-z0-9])([A-Z])/g, "$1 $2");
}

function SnapshotRestore({ event }: { event: EventRecord }) {
  const t = useTranslations("Activity");
  const snapshotId = event.operation_snapshot_id;
  const { data: preview, error } = useOperationPreview(snapshotId);
  const restore = useRestoreOperation(snapshotId);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const restoresFileLocation = event.type === "RootVideoOrganized";
  if (!snapshotId) return null;

  const actionLabel = restoresFileLocation ? t("restoreFileLocation") : t("restore");
  const confirmation = restoresFileLocation ? t("restoreFileLocationConfirm") : t("restoreConfirm");

  const handleConfirmRestore = async () => {
    if (!preview?.confirmation_token) return;
    try {
      await restore.trigger({ confirmation_token: preview.confirmation_token });
      await mutate(API.activityEvents());
    } catch {
      // SWR mutation exposes the error state via restore.error.
    } finally {
      setConfirmOpen(false);
    }
  };

  return (
    <div className="mt-4 space-y-3 border-t border-line pt-4">
      {error && <InlineFeedback tone="error">{t("snapshotPreviewFailed")}</InlineFeedback>}
      {!preview && !error && <Spinner className="h-4 w-4" />}
      {preview && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="border border-line bg-canvas p-3">
              <span className="type-meta block text-ink-subtle">{t("before")}</span>
              <code className="mt-1.5 block break-all font-mono text-xs leading-5 text-ink-muted">{JSON.stringify(preview.before)}</code>
            </div>
            <div className="border border-line bg-canvas p-3">
              <span className="type-meta block text-ink-subtle">{t("after")}</span>
              <code className="mt-1.5 block break-all font-mono text-xs leading-5 text-ink-muted">{JSON.stringify(preview.after)}</code>
            </div>
          </div>
          <Button
            onClick={() => setConfirmOpen(true)}
            disabled={!preview.current_matches_after || !preview.confirmation_token || preview.status !== "available"}
            busy={restore.isMutating}
            variant="danger"
          >
            <RotateCcw className="h-4 w-4" />
            {actionLabel}
          </Button>
          <Dialog
            open={confirmOpen}
            onClose={() => { if (!restore.isMutating) setConfirmOpen(false); }}
            size="sm"
            ariaLabel={actionLabel}
            closeLabel={t("cancel")}
            panelClassName="p-6"
          >
            <h3 className="type-section-title text-ink">{actionLabel}</h3>
            <p className="mt-3 text-sm leading-relaxed text-ink-muted">{confirmation}</p>
            <div className="mt-6 flex items-center justify-end gap-3">
              <Button variant="ghost" onClick={() => setConfirmOpen(false)} disabled={restore.isMutating}>
                {t("cancel")}
              </Button>
              <Button variant="danger" busy={restore.isMutating} onClick={() => void handleConfirmRestore()}>
                <RotateCcw className="h-4 w-4" />
                {actionLabel}
              </Button>
            </div>
          </Dialog>
          {restore.error && <InlineFeedback tone="error">{t("restoreConflict")}</InlineFeedback>}
        </>
      )}
    </div>
  );
}

export default function LibraryActivityClient() {
  const t = useTranslations("Activity");
  const [aggregateType, setAggregateType] = useState("");
  const [aggregateId, setAggregateId] = useState("");
  const [eventType, setEventType] = useState("");
  const [expanded, setExpanded] = useState<string[]>([]);
  const url = useMemo(() => API.activityEvents({
    aggregate_type: aggregateType || undefined,
    aggregate_id: aggregateId.trim() || undefined,
    type: eventType.trim() || undefined,
    limit: 100,
  }), [aggregateId, aggregateType, eventType]);
  const { data: events = [], isLoading, error } = useSWR<EventRecord[]>(url, { refreshInterval: 5000 });

  return (
    <div className="space-y-8">
      <section className="grid gap-3 border-y border-line py-5 sm:grid-cols-3">
        <FormField label={t("aggregate")}>
          <Select value={aggregateType} onChange={(event) => setAggregateType(event.target.value)}>
            <option value="">{t("all")}</option>
            {aggregateTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </Select>
        </FormField>
        <FormField label={t("aggregateId")}>
          <TextInput value={aggregateId} onChange={(event) => setAggregateId(event.target.value)} placeholder={t("aggregateIdPlaceholder")} />
        </FormField>
        <FormField label={t("eventType")}>
          <TextInput value={eventType} onChange={(event) => setEventType(event.target.value)} placeholder={t("eventTypePlaceholder")} />
        </FormField>
      </section>

      <div className="flex items-center justify-between type-meta text-ink-subtle">
        <span className="inline-flex items-center gap-2"><Filter className="h-3.5 w-3.5" />{t("eventCount", { count: events.length })}</span>
        {isLoading && <Spinner className="h-4 w-4" />}
      </div>

      {error ? (
        <StateMessage state="error">{t("loadFailed")}</StateMessage>
      ) : events.length === 0 ? (
        <StateMessage>{t("empty")}</StateMessage>
      ) : (
        <ol className="space-y-3">
          {events.map((event) => {
            const open = expanded.includes(event.id);
            return (
              <li key={event.id} className="border border-line bg-surface/40 p-4">
                <button
                  type="button"
                  onClick={() => setExpanded((items) => open ? items.filter((id) => id !== event.id) : [...items, event.id])}
                  className="focus-ring flex w-full items-start justify-between gap-5 text-left"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-3">
                      <ChevronDown className={`h-4 w-4 shrink-0 transition-transform duration-fast ${open ? "" : "-rotate-90"}`} />
                      <p className="truncate font-bold text-ink">{eventLabel(event.type)}</p>
                    </div>
                    <p className="mt-2 truncate type-meta text-ink-subtle">
                      {event.aggregate_type} · {event.aggregate_id || t("global")}
                    </p>
                  </div>
                  <time className="flex shrink-0 items-center gap-2 type-meta text-ink-subtle">
                    <Clock className="h-3.5 w-3.5" />{formatTime(event.occurred_at)}
                  </time>
                </button>
                {open && (
                  <div className="mt-4 space-y-3 pl-7">
                    {event.display_title && event.film_id ? (
                      <Link href={`/library/${event.film_id}`} className="font-bold text-ink hover:underline">{event.display_title}</Link>
                    ) : null}
                    <pre className="scrollbar-minimal max-h-56 overflow-auto whitespace-pre-wrap break-all border border-line bg-canvas p-3 font-mono text-xs leading-5 text-ink-muted">
                      {JSON.stringify(event.payload || {}, null, 2)}
                    </pre>
                    <SnapshotRestore event={event} />
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
