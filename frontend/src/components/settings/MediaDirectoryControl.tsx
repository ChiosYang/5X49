"use client";

import { useEffect, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Loader2, TriangleAlert } from "lucide-react";
import FileBrowser from "@/components/FileBrowser";
import { Button } from "@/components/ui/Button";
import { InlineFeedback } from "@/components/ui/Feedback";
import { TextInput } from "@/components/ui/FormControls";
import {
  useMediaDir,
  useUpdateMediaDir,
} from "@/hooks/useSettings";
import { isMediaDirectoryReady } from "@/lib/library-onboarding";

export default function MediaDirectoryControl({
  autoSave = false,
  inlineStatus = false,
  showDockerNote = false,
}: {
  autoSave?: boolean;
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
  const browseButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!saveResult) return;
    const timer = window.setTimeout(() => resetSave(), 3000);
    return () => window.clearTimeout(timer);
  }, [resetSave, saveResult]);

  const value = draft ?? data?.media_dir ?? "";
  const dirty = draft !== undefined && draft.trim() !== (data?.media_dir ?? "");
  const ready = isMediaDirectoryReady(saveResult ?? data);
  const inlineIconState = (() => {
    if (!inlineStatus) return null;
    if (saving || isLoading) return "loading";
    if (loadError || saveError) return "error";
    if (ready && !dirty) return "ready";
    return null;
  })();
  const saveErrorMessage = (() => {
    if (!(saveError instanceof Error)) return t("mediaDirSaveFailed");
    if (saveError.message === "Media directory cannot be empty") return t("mediaDirEmpty");
    if (saveError.message === "Media directory does not exist") return t("mediaDirMissing");
    if (saveError.message === "Media directory is not readable") return t("mediaDirNotReadable");
    return saveError.message;
  })();

  const saveMediaDirectory = async (nextValue: string) => {
    const trimmedValue = nextValue.trim();
    if (!trimmedValue || saving) return;

    try {
      await updateMediaDir(trimmedValue);
      setDraft(undefined);
    } catch {
      // Mutation state renders the backend validation detail below.
    }
  };

  const handleSave = () => saveMediaDirectory(value);

  const handleDraftChange = (nextValue: string) => {
    resetSave();
    setDraft(nextValue);
  };

  const handleInputBlur = (event: FocusEvent<HTMLInputElement>) => {
    if (!autoSave || !dirty || event.relatedTarget === browseButtonRef.current) return;
    void saveMediaDirectory(value);
  };

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (!autoSave || event.key !== "Enter" || !dirty) return;
    event.preventDefault();
    void saveMediaDirectory(value);
  };

  return (
    <>
      <div className="flex flex-col gap-3 md:flex-row">
        <div className="relative min-w-0 flex-1">
          <TextInput
            type="text"
            value={value}
            onChange={(event) => handleDraftChange(event.target.value)}
            onBlur={handleInputBlur}
            onKeyDown={handleInputKeyDown}
            aria-label={t("mediaDir")}
            placeholder="/path/to/movies"
            className={inlineStatus ? "pr-12" : undefined}
          />
          {inlineIconState === "loading" ? (
            <Loader2
              aria-label={t("mediaDirChecking")}
              role="status"
              className="absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 animate-spin text-ink-muted"
            />
          ) : inlineIconState === "error" ? (
            <TriangleAlert
              aria-hidden="true"
              className="absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 text-danger"
            />
          ) : inlineIconState === "ready" ? (
            <CheckCircle2
              aria-label={t("mediaDirReady")}
              role="status"
              className="absolute top-1/2 right-4 h-4 w-4 -translate-y-1/2 text-success"
            />
          ) : null}
        </div>
        <Button
          ref={browseButtonRef}
          onClick={() => setFileBrowserOpen(true)}
          disabled={autoSave && saving}
        >
          {t("browse")}
        </Button>
        {!autoSave ? (
          <Button
            onClick={handleSave}
            disabled={!dirty || !value.trim() || saving}
            busy={saving}
            variant="primary"
          >
            {saving ? t("saving") : t("save")}
          </Button>
        ) : null}
      </div>

      {!inlineStatus || loadError || saveError ? (
        <div className="mt-3 min-h-5" aria-live="polite">
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
      ) : null}

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
            if (autoSave) void saveMediaDirectory(path);
          }}
          onCancel={() => setFileBrowserOpen(false)}
        />
      ) : null}
    </>
  );
}
