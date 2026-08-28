"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2 } from "lucide-react";
import FileBrowser from "@/components/FileBrowser";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";
import {
  useMediaDir,
  useUpdateMediaDir,
} from "@/hooks/useSettings";
import { cn } from "@/lib/cn";
import { isMediaDirectoryReady } from "@/lib/library-onboarding";

export default function MediaDirectoryControl({
  inlineStatus = false,
  showDockerNote = false,
}: {
  inlineStatus?: boolean;
  showDockerNote?: boolean;
}) {
  const t = useTranslations("Settings");
  const { data, error: loadError, isLoading } = useMediaDir();
  const {
    trigger: updateMediaDir,
    isMutating: saving,
    data: saveResult,
    error: saveError,
    reset: resetSave,
  } = useUpdateMediaDir();
  const [draft, setDraft] = useState<string>();
  const [fileBrowserOpen, setFileBrowserOpen] = useState(false);

  useEffect(() => {
    if (!saveResult) return;
    const timer = window.setTimeout(() => resetSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [resetSave, saveResult]);

  const value = draft ?? data?.media_dir ?? "";
  const dirty = draft !== undefined && draft.trim() !== (data?.media_dir ?? "");
  const ready = isMediaDirectoryReady(data);
  const showReadyInInput =
    inlineStatus && ready && !dirty && !isLoading && !loadError && !saveError && !saveResult;
  const saveErrorMessage = (() => {
    if (!(saveError instanceof Error)) return t("mediaDirSaveFailed");
    if (saveError.message === "Media directory cannot be empty") return t("mediaDirEmpty");
    if (saveError.message === "Media directory does not exist") return t("mediaDirMissing");
    if (saveError.message === "Media directory is not readable") return t("mediaDirNotReadable");
    return saveError.message;
  })();

  const handleSave = async () => {
    try {
      await updateMediaDir(value.trim());
      setDraft(undefined);
    } catch {
      // Mutation state renders the backend validation detail below.
    }
  };

  const handleDraftChange = (nextValue: string) => {
    resetSave();
    setDraft(nextValue);
  };

  return (
    <>
      <div className="flex flex-col gap-3 md:flex-row">
        <div className="relative min-w-0 flex-1">
          <TextInput
            type="text"
            value={value}
            onChange={(event) => handleDraftChange(event.target.value)}
            aria-label={t("mediaDir")}
            placeholder="/path/to/movies"
            className={inlineStatus ? "pr-12" : undefined}
          />
          {showReadyInInput ? (
            <CheckCircle2
              aria-hidden="true"
              className="absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 text-success"
            />
          ) : null}
        </div>
        <Button onClick={() => setFileBrowserOpen(true)}>
          {t("browse")}
        </Button>
        <Button
          onClick={handleSave}
          disabled={!dirty || !value.trim() || saving}
          busy={saving}
          variant="primary"
        >
          {saving ? t("saving") : t("save")}
        </Button>
      </div>

      <div
        className={cn("mt-3 min-h-5", showReadyInInput && "sr-only")}
        aria-live="polite"
      >
        {loadError ? (
          <InlineFeedback tone="error">{t("mediaDirLoadFailed")}</InlineFeedback>
        ) : saveError ? (
          <InlineFeedback tone="error">{saveErrorMessage}</InlineFeedback>
        ) : saveResult ? (
          <InlineFeedback tone="success">{t("mediaDirSavedReady")}</InlineFeedback>
        ) : isLoading ? (
          <InlineFeedback>{t("mediaDirChecking")}</InlineFeedback>
        ) : ready ? (
          <InlineFeedback tone="success">{t("mediaDirReady")}</InlineFeedback>
        ) : (
          <InlineFeedback tone="warning">{t("mediaDirUnavailable")}</InlineFeedback>
        )}
      </div>

      {showDockerNote ? (
        <p className="mt-3 text-xs leading-5 text-ink-disabled">{t("noteDocker")}</p>
      ) : null}

      {fileBrowserOpen ? (
        <FileBrowser
          isOpen={fileBrowserOpen}
          initialPath={value}
          onSelect={(path) => {
            handleDraftChange(path);
            setFileBrowserOpen(false);
          }}
          onCancel={() => setFileBrowserOpen(false)}
        />
      ) : null}
    </>
  );
}
