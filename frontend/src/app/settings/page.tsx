"use client";

import { useState } from "react";

type SettingSection = "appearance" | "display" | "analysis" | "library";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<SettingSection>("appearance");

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

      {/* Two-Column Layout */}
      <div className="flex flex-col md:flex-row min-h-[60vh]">
        {/* Left Sidebar Navigation */}
        <aside className="w-full md:w-64 border-b md:border-b-0 md:border-r border-neutral-900 bg-black">
          <nav className="sticky top-0 p-8 md:p-12 space-y-2">
            <button
              onClick={() => setActiveSection("appearance")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "appearance"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              Appearance
            </button>
            <button
              onClick={() => setActiveSection("display")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "display"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              Display
            </button>
            <button
              onClick={() => setActiveSection("analysis")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "analysis"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              AI Analysis
            </button>
            <button
              onClick={() => setActiveSection("library")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "library"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              Library
            </button>
          </nav>
        </aside>

        {/* Right Content Area */}
        <main className="flex-1 p-8 md:p-16">
          <div className="max-w-3xl">
            {/* Appearance Section */}
            {activeSection === "appearance" && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">Appearance</h2>
                  <p className="text-sm text-neutral-500 mb-8">Customize the visual experience</p>
                </div>

                {/* Settings items will go here */}
                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Animations</p>
                        <p className="text-xs text-neutral-600">Enable page transitions and effects</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Compact Mode</p>
                        <p className="text-xs text-neutral-600">Reduce spacing in list views</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* Display Section */}
            {activeSection === "display" && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">Display</h2>
                  <p className="text-sm text-neutral-500 mb-8">Control how films are shown</p>
                </div>

                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Default Sort</p>
                        <p className="text-xs text-neutral-600">Choose default sorting method</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Poster Quality</p>
                        <p className="text-xs text-neutral-600">High quality or fast loading</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* AI Analysis Section */}
            {activeSection === "analysis" && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">AI Analysis</h2>
                  <p className="text-sm text-neutral-500 mb-8">Configure genealogy analysis behavior</p>
                </div>

                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Auto Analyze</p>
                        <p className="text-xs text-neutral-600">Automatically analyze new films</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Language Preference</p>
                        <p className="text-xs text-neutral-600">Chinese or English analysis</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>
                </div>
              </div>
            )}

            {/* Library Section */}
            {activeSection === "library" && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">Library</h2>
                  <p className="text-sm text-neutral-500 mb-8">Manage your film collection</p>
                </div>

                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Media Directory</p>
                        <p className="text-xs text-neutral-600">Path to NFO files (Docker only)</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Auto Scan</p>
                        <p className="text-xs text-neutral-600">Periodically check for new films</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
