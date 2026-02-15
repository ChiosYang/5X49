"use client";

import { useState, useEffect, useMemo } from "react";
import API from "@/lib/api";

type SettingSection = "appearance" | "display" | "analysis" | "library";

export default function SettingsPage() {
  const [activeSection, setActiveSection] = useState<SettingSection>("appearance");
  const [currentModel, setCurrentModel] = useState<string>("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [modelSearch, setModelSearch] = useState<string>("");
  const [dropdownOpen, setDropdownOpen] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [apiTesting, setApiTesting] = useState(false);
  const [apiTestResult, setApiTestResult] = useState<{status: string; message: string} | null>(null);
  const [baseUrl, setBaseUrl] = useState<string>("");
  const [baseUrlSaving, setBaseUrlSaving] = useState(false);
  const [baseUrlSaved, setBaseUrlSaved] = useState(false);

  // Filter models based on search
  const filteredModels = useMemo(() => {
    if (!modelSearch.trim()) return availableModels;
    const search = modelSearch.toLowerCase();
    return availableModels.filter(model => 
      model.toLowerCase().includes(search)
    );
  }, [availableModels, modelSearch]);

  // Load model settings on mount
  useEffect(() => {
    fetchModelSettings();
    fetchBaseUrl();
  }, []);

  const fetchModelSettings = async () => {
    try {
      const res = await fetch(API.settingsModel());
      if (res.ok) {
        const data = await res.json();
        setCurrentModel(data.current_model);
        setAvailableModels(data.available_models);
      }
    } catch (error) {
      console.error("Failed to load model settings:", error);
    }
  };

  const fetchBaseUrl = async () => {
    try {
      const res = await fetch(API.settingsBaseUrl());
      if (res.ok) {
        const data = await res.json();
        setBaseUrl(data.base_url);
      }
    } catch (error) {
      console.error("Failed to load base URL:", error);
    }
  };

  const handleModelChange = async (newModel: string) => {
    setLoading(true);
    setSaved(false);
    try {
      const res = await fetch(`${API.settingsModel()}?model_name=${encodeURIComponent(newModel)}`, {
        method: "PUT",
      });
      if (res.ok) {
        setCurrentModel(newModel);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch (error) {
      console.error("Failed to update model:", error);
    } finally {
      setLoading(false);
    }
  };

  const testApiKey = async () => {
    setApiTesting(true);
    setApiTestResult(null);
    try {
      const res = await fetch(API.settingsTestApiKey());
      if (res.ok) {
        const data = await res.json();
        setApiTestResult(data);
      }
    } catch (error) {
      setApiTestResult({
        status: "error",
        message: "Failed to connect to backend"
      });
    } finally {
      setApiTesting(false);
    }
  };

  const handleBaseUrlChange = async () => {
    setBaseUrlSaving(true);
    setBaseUrlSaved(false);
    try {
      const res = await fetch(`${API.settingsBaseUrl()}?base_url=${encodeURIComponent(baseUrl)}`, {
        method: "PUT",
      });
      if (res.ok) {
        setBaseUrlSaved(true);
        setTimeout(() => setBaseUrlSaved(false), 3000);
      }
    } catch (error) {
      console.error("Failed to update base URL:", error);
    } finally {
      setBaseUrlSaving(false);
    }
  };

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
                  {/* Model Selector - Custom Searchable Dropdown */}
                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">AI Model</p>
                        <p className="text-xs text-neutral-600 mb-4">Choose the LLM for genealogy analysis</p>
                        
                        {/* Custom Dropdown */}
                        <div className="relative">
                          {/* Current Selection / Trigger */}
                          <button
                            type="button"
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                            className="w-full bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-sm uppercase tracking-widest hover:border-neutral-600 focus:border-white focus:outline-none text-left flex items-center justify-between"
                          >
                            <span>{currentModel || "Select a model..."}</span>
                            <svg 
                              className={`w-4 h-4 transition-transform ${dropdownOpen ? 'rotate-180' : ''}`} 
                              fill="none" 
                              stroke="currentColor" 
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                          </button>

                          {/* Dropdown Menu */}
                          {dropdownOpen && (
                            <>
                              {/* Backdrop to close dropdown */}
                              <div 
                                className="fixed inset-0 z-10" 
                                onClick={() => setDropdownOpen(false)}
                              />
                              
                              {/* Dropdown Content */}
                              <div className="absolute z-20 w-full mt-1 bg-neutral-900 border border-neutral-800 shadow-2xl max-h-96 flex flex-col">
                                {/* Search Box Inside Dropdown */}
                                <div className="p-3 border-b border-neutral-800">
                                  <input
                                    type="text"
                                    placeholder="Search models..."
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    className="w-full bg-neutral-950 border border-neutral-700 text-white px-3 py-2 text-sm placeholder:text-neutral-600 focus:border-white focus:outline-none"
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                  {modelSearch && (
                                    <p className="text-xs text-neutral-500 mt-2">
                                      {filteredModels.length} model{filteredModels.length !== 1 ? 's' : ''} found
                                    </p>
                                  )}
                                </div>

                                {/* Model List */}
                                <div className="overflow-y-auto max-h-80">
                                  {filteredModels.length > 0 ? (
                                    filteredModels.map((model) => (
                                      <button
                                        key={model}
                                        type="button"
                                        onClick={() => {
                                          handleModelChange(model);
                                          setDropdownOpen(false);
                                          setModelSearch("");
                                        }}
                                        className={`w-full text-left px-4 py-3 text-sm hover:bg-neutral-800 transition-colors ${
                                          currentModel === model ? 'bg-white text-black font-medium' : 'text-white'
                                        }`}
                                      >
                                        {model}
                                      </button>
                                    ))
                                  ) : (
                                    <div className="px-4 py-8 text-center text-neutral-600 text-sm">
                                      No models found
                                    </div>
                                  )}
                                </div>
                              </div>
                            </>
                          )}
                        </div>
                        
                        {saved && (
                          <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ Saved</p>
                        )}
                        {loading && (
                          <p className="text-xs text-neutral-500 mt-2 uppercase tracking-widest">Saving...</p>
                        )}
                      </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <label className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">Auto Analyze</p>
                        <p className="text-xs text-neutral-600">Automatically analyze new films</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">Coming Soon</div>
                    </label>
                  </div>

                  {/* Test API Key */}
                  <div className="border-b border-neutral-900 pb-6">
                    <div>
                      <p className="text-sm font-medium uppercase tracking-widest mb-1">API Connection</p>
                      <p className="text-xs text-neutral-600 mb-4">Test OpenRouter API key connectivity</p>
                      
                      <button
                        onClick={testApiKey}
                        disabled={apiTesting}
                        className="bg-white text-black px-6 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {apiTesting ? "Testing..." : "Test API Key"}
                      </button>

                      {apiTestResult && (
                        <div className={`mt-4 p-4 border ${
                          apiTestResult.status === "success" 
                            ? "border-green-500 bg-green-500/10" 
                            : "border-red-500 bg-red-500/10"
                        }`}>
                          <p className={`text-sm ${
                            apiTestResult.status === "success" ? "text-green-500" : "text-red-500"
                          }`}>
                            {apiTestResult.status === "success" ? "✓" : "✗"} {apiTestResult.message}
                          </p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* API Base URL */}
                  <div className="border-b border-neutral-900 pb-6">
                    <div>
                      <p className="text-sm font-medium uppercase tracking-widest mb-1">API Base URL</p>
                      <p className="text-xs text-neutral-600 mb-4">Configure the API endpoint for model requests</p>
                      
                      <div className="flex gap-3">
                        <input
                          type="text"
                          value={baseUrl}
                          onChange={(e) => setBaseUrl(e.target.value)}
                          placeholder="https://openrouter.ai/api/v1"
                          className="flex-1 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-sm placeholder:text-neutral-600 hover:border-neutral-600 focus:border-white focus:outline-none"
                        />
                        <button
                          onClick={handleBaseUrlChange}
                          disabled={baseUrlSaving}
                          className="bg-white text-black px-6 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {baseUrlSaving ? "Saving..." : "Save"}
                        </button>
                      </div>

                      {baseUrlSaved && (
                        <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ Saved</p>
                      )}
                      
                      <div className="mt-4 space-y-2 text-xs text-neutral-600">
                        <p className="font-medium text-neutral-500">Common Providers:</p>
                        <button
                          onClick={() => setBaseUrl("https://openrouter.ai/api/v1")}
                          className="block hover:text-white transition-colors"
                        >
                          • OpenRouter: https://openrouter.ai/api/v1
                        </button>
                        <button
                          onClick={() => setBaseUrl("https://api.openai.com/v1")}
                          className="block hover:text-white transition-colors"
                        >
                          • OpenAI: https://api.openai.com/v1
                        </button>
                        <button
                          onClick={() => setBaseUrl("https://api.anthropic.com/v1")}
                          className="block hover:text-white transition-colors"
                        >
                          • Anthropic: https://api.anthropic.com/v1
                        </button>
                      </div>
                    </div>
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
