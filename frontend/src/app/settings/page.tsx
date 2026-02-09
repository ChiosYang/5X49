"use client";

export default function SettingsPage() {
  return (
    <div className="min-h-screen bg-black text-white">
      {/* Hero Section */}
      <div className="border-b border-neutral-900 px-8 md:px-16 py-16 md:py-24">
        <h1 className="text-5xl md:text-7xl font-bold uppercase tracking-tight mb-4">
          Settings
        </h1>
        <p className="text-sm text-neutral-500 uppercase tracking-widest">
          Configure your film genealogy experience
        </p>
      </div>

      {/* Content Area - Empty for now */}
      <div className="px-8 md:px-16 py-16">
        <div className="max-w-4xl">
          <p className="text-neutral-600 text-sm uppercase tracking-widest">
            Settings configuration coming soon
          </p>
        </div>
      </div>
    </div>
  );
}
