import DiaryClient from "./DiaryClient";

export default async function DiaryPage() {
  return (
    <div className="page-x min-h-screen bg-canvas py-6 text-ink selection:bg-inverse selection:text-inverse-ink md:py-12">
      <div className="w-full space-y-12 pt-32">
        <DiaryClient />
      </div>
    </div>
  );
}
