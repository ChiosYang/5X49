import { getTranslations } from "next-intl/server";
import LibraryActivityClient from "./LibraryActivityClient";

export default async function LibraryActivityPage() {
  const t = await getTranslations("Activity");

  return (
    <div className="min-h-screen bg-black px-8 py-6 text-white selection:bg-white selection:text-black md:px-12 md:py-12">
      <div className="w-full space-y-12 pt-32">
        <header className="border-b border-neutral-900 pb-8">
          <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
            {t("eyebrow")}
          </span>
          <h1 className="mt-4 font-serif text-6xl leading-none tracking-tighter md:text-9xl">
            {t("title")}
          </h1>
        </header>
        <LibraryActivityClient />
      </div>
    </div>
  );
}
