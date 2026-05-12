"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { FolderInput, Loader2 } from "lucide-react";
import { useOrganizeRootVideos } from "@/hooks/useSettings";

export default function LibraryOrganizeRootButton() {
  const t = useTranslations("Library");
  const router = useRouter();
  const { trigger, isMutating, error } = useOrganizeRootVideos();

  const handleOrganize = async () => {
    await trigger();
    router.refresh();
  };

  return (
    <button
      type="button"
      onClick={handleOrganize}
      disabled={isMutating}
      className={`flex h-10 w-10 items-center justify-center border bg-neutral-950 text-white transition-colors hover:bg-neutral-900 disabled:cursor-not-allowed disabled:opacity-50 ${
        error
          ? "border-red-700 hover:border-red-500"
          : "border-neutral-800 hover:border-neutral-500"
      }`}
      aria-label={error ? t("organizeRootFailed") : t("organizeRoot")}
      title={error ? t("organizeRootFailed") : t("organizeRoot")}
    >
      {isMutating ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <FolderInput className="h-4 w-4" />
      )}
    </button>
  );
}
