import { getTranslations } from "next-intl/server";

import DiaryClient from "./DiaryClient";

export default async function DiaryPage() {
  const t = await getTranslations("Diary");
  return (
    <div className="min-h-screen bg-canvas px-5 py-6 text-ink sm:px-8 md:px-12 md:py-12">
      <div className="w-full space-y-12 pt-32">
        <header className="border-b border-line pb-8">
          <p className="type-label text-ink-subtle">{t("eyebrow")}</p>
          <h1 className="mt-3 type-display-editorial text-ink">{t("title")}</h1>
          <p className="mt-4 max-w-2xl text-sm font-bold tracking-widest text-ink-subtle uppercase">
            {t("subtitle")}
          </p>
        </header>
        <DiaryClient />
      </div>
    </div>
  );
}
