"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { RotateCcw, ServerOff } from "lucide-react";
import { Button } from "@/components/ui/Button";

export default function RouteError({
  error,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("Errors");

  useEffect(() => {
    console.error("Route rendering failed", error);
  }, [error]);

  return (
    <div className="page-x flex min-h-screen items-center justify-center bg-canvas py-24 text-ink">
      <section className="w-full max-w-2xl border-y border-line py-12 text-center">
        <ServerOff className="mx-auto h-8 w-8 text-ink-disabled" aria-hidden="true" />
        <p className="type-label mt-6 text-ink-disabled">{t("eyebrow")}</p>
        <h1 className="mt-3 font-serif text-4xl tracking-tight md:text-6xl">{t("title")}</h1>
        <p className="mx-auto mt-5 max-w-xl text-sm leading-6 text-ink-subtle">{t("description")}</p>
        <div className="mx-auto mt-6 max-w-lg bg-surface p-4 text-left text-xs leading-5 text-ink-muted">
          <p>{t("checkBackend")}</p>
          <code className="mt-2 block break-all text-ink-subtle">docker compose ps</code>
        </div>
        <Button
          className="mt-8"
          variant="primary"
          icon={<RotateCcw className="h-4 w-4" />}
          onClick={() => window.location.reload()}
        >
          {t("retry")}
        </Button>
      </section>
    </div>
  );
}
