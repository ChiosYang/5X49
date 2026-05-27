import AdminTools from "@/components/AdminTools";

export default function AdminHealthPage() {
  const isDevelopment = process.env.NODE_ENV === "development";

  return (
    <div className="min-h-screen bg-black px-8 py-6 text-white selection:bg-white selection:text-black md:px-12 md:py-12">
      <div className="w-full space-y-12 pt-32">
        <header className="border-b border-neutral-900 pb-8">
          <span className="block text-xs font-bold uppercase tracking-widest text-neutral-500">
            Admin
          </span>
          <h1 className="mt-4 font-serif text-6xl leading-none tracking-tighter md:text-9xl">
            Health
          </h1>
        </header>

        {isDevelopment ? (
          <AdminTools />
        ) : (
          <section className="border border-neutral-900 bg-neutral-950/50 p-5 text-sm leading-relaxed text-neutral-400">
            Developer health tools are not available in this environment.
          </section>
        )}
      </div>
    </div>
  );
}
