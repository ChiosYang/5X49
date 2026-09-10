import DiaryClient from "./DiaryClient";

export default async function DiaryPage() {
  return (
    <div className="min-h-screen bg-canvas px-5 py-6 text-ink sm:px-8 md:px-12 md:py-12">
      <div className="w-full space-y-12 pt-32">
        <DiaryClient />
      </div>
    </div>
  );
}
