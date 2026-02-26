"use client";

import { useState, useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "@/i18n/routing";

// ... (inside SettingsPage component)

import FileBrowser from "@/components/FileBrowser";
import LibrarianTerminal from "@/components/LibrarianTerminal";
import API from "@/lib/api";

type SettingSection = "appearance" | "display" | "analysis" | "library";

export default function SettingsPage() {
  const t = useTranslations("Settings");
  const router = useRouter();
  const pathname = usePathname();
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
  const [fileBrowserOpen, setFileBrowserOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [language, setLanguage] = useState<"zh" | "en">("zh");
  const [languageSaving, setLanguageSaving] = useState(false);

  // Scan State
  const [isScanning, setIsScanning] = useState(false);
  const [scanMessage, setScanMessage] = useState("");

  const handleScanLibrary = async () => {
    setIsScanning(true);
    setScanMessage("");
    try {
      const res = await fetch(API.systemScanLibrary(), {
        method: "POST",
      });
      if (res.ok) {
        setScanMessage("Scan started in background");
        setTimeout(() => setScanMessage(""), 5000);
      } else {
        setScanMessage("Failed to start scan");
      }
    } catch (error) {
      console.error("Scan failed:", error);
      setScanMessage("Network error");
    } finally {
      setIsScanning(false);
    }
  };

  // Filter models based on search
  const filteredModels = useMemo(() => {
    if (!modelSearch.trim()) return availableModels;
    const search = modelSearch.toLowerCase();
    return availableModels.filter((model: string) => 
      model.toLowerCase().includes(search)
    );
  }, [availableModels, modelSearch]);

  // Load model settings on mount
  useEffect(() => {
    fetchModelSettings();
    fetchBaseUrl();
    fetchMediaDir();
    fetchLanguage();
  }, []);

  const fetchLanguage = async () => {
    try {
      const res = await fetch(API.settingsLanguage());
      if (res.ok) {
        const data = await res.json();
        setLanguage(data.language);
      }
    } catch (error) {
      console.error("Failed to fetch language:", error);
    }
  };

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
      console.error("Failed to fetch base URL:", error);
    }
  };

  // State for Media Path
  const [mediaDir, setMediaDir] = useState<string>("");
  const [mediaDirSaving, setMediaDirSaving] = useState(false);
  const [mediaDirSaved, setMediaDirSaved] = useState(false);

  // Fetch Media Path
  const fetchMediaDir = async () => {
    try {
      const res = await fetch(API.settingsMediaDir());
      if (res.ok) {
        const data = await res.json();
        setMediaDir(data.media_dir);
      }
    } catch (error) {
      console.error("Failed to fetch media dir:", error);
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

  const handleLanguageChange = async (lang: "zh" | "en") => {
    if (lang === language) return;
    setLanguageSaving(true);
    try {
      const res = await fetch(`${API.settingsLanguage()}?language=${lang}`, {
        method: "PUT",
      });
      if (res.ok) {
        setLanguage(lang);
        router.replace({ pathname }, { locale: lang });
      }
    } catch (error) {
      console.error("Failed to update language:", error);
    } finally {
      setLanguageSaving(false);
    }
  };

  const handleMediaDirChange = async () => {
    setMediaDirSaving(true);
    try {
      const res = await fetch(`${API.settingsMediaDir()}?media_dir=${encodeURIComponent(mediaDir)}`, {
        method: "PUT",
      });
      if (res.ok) {
        setMediaDirSaved(true);
        setTimeout(() => setMediaDirSaved(false), 2000);
      }
    } catch (error) {
      console.error("Failed to save media dir:", error);
    } finally {
      setMediaDirSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Hero Section */}
      <div className="border-b border-neutral-900 px-8 md:px-16 py-16 md:py-24">
        <h1 className="text-5xl md:text-7xl font-bold uppercase tracking-tight mb-4">
          {t("title")}
        </h1>
        <p className="text-sm text-neutral-500 uppercase tracking-widest">
          {t("subtitle")}
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
              {t("appearance")}
            </button>
            <button
              onClick={() => setActiveSection("display")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "display"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              {t("display")}
            </button>
            <button
              onClick={() => setActiveSection("analysis")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "analysis"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              {t("analysis")}
            </button>
            <button
              onClick={() => setActiveSection("library")}
              className={`block w-full text-left px-4 py-3 text-sm font-medium uppercase tracking-widest transition-colors ${
                activeSection === "library"
                  ? "bg-white text-black"
                  : "text-neutral-500 hover:text-white hover:bg-neutral-900"
              }`}
            >
              {t("library")}
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
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">{t("appearance")}</h2>
                  <p className="text-sm text-neutral-500 mb-8">Customize the visual experience</p>
                </div>

                {/* Settings items will go here */}
                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("languagePref")}</p>
                        <p className="text-xs text-neutral-600">{t("languageDesc")}</p>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="flex bg-neutral-900 border border-neutral-800 p-1">
                          <button
                            onClick={() => handleLanguageChange("zh")}
                            disabled={languageSaving}
                            className={`px-4 py-2 text-xs font-medium uppercase tracking-widest transition-colors ${
                              language === "zh" ? "bg-white text-black" : "text-neutral-500 hover:text-white"
                            }`}
                          >
                            ZH
                          </button>
                          <button
                            onClick={() => handleLanguageChange("en")}
                            disabled={languageSaving}
                            className={`px-4 py-2 text-xs font-medium uppercase tracking-widest transition-colors ${
                              language === "en" ? "bg-white text-black" : "text-neutral-500 hover:text-white"
                            }`}
                          >
                            EN
                          </button>
                        </div>
                        {languageSaving && <Loader2 className="w-4 h-4 animate-spin text-neutral-500" />}
                      </div>
                    </div>
                  </div>

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
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">{t("display")}</h2>
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
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">{t("analysis")}</h2>
                  <p className="text-sm text-neutral-500 mb-8">Configure genealogy analysis behavior</p>
                </div>

                <div className="space-y-6">
                  {/* Model Selector - Custom Searchable Dropdown */}
                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("model")}</p>
                        <p className="text-xs text-neutral-600 mb-4">{t("modelDesc")}</p>
                        
                        {/* Custom Dropdown */}
                        <div className="relative">
                          {/* Current Selection / Trigger */}
                          <button
                            onClick={() => setDropdownOpen(!dropdownOpen)}
                            className="w-full flex items-center justify-between bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-sm hover:border-neutral-600 focus:outline-none"
                          >
                            <span className="truncate">{currentModel || "Select a model..."}</span>
                            <span className="text-neutral-500 ml-2">▼</span>
                          </button>

                          {/* Dropdown Menu */}
                          {dropdownOpen && (
                            <>
                              <div 
                                className="fixed inset-0 z-10"
                                onClick={() => setDropdownOpen(false)}
                              />
                              <div className="absolute z-20 mt-2 w-full bg-neutral-900 border border-neutral-800 shadow-xl max-h-60 flex flex-col">
                                <div className="p-2 border-b border-neutral-800">
                                  <input
                                    type="text"
                                    value={modelSearch}
                                    onChange={(e) => setModelSearch(e.target.value)}
                                    placeholder="Search models..."
                                    className="w-full bg-neutral-950 text-white px-3 py-2 text-xs focus:outline-none"
                                    autoFocus
                                  />
                                </div>
                                <div className="overflow-y-auto flex-1">
                                  {filteredModels.length > 0 ? (
                                    filteredModels.map((model: string) => (
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
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("autoAnalyze")}</p>
                        <p className="text-xs text-neutral-600">{t("autoAnalyzeDesc")}</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">{t("comingSoon")}</div>
                    </label>
                  </div>

                  {/* Test API Key */}
                  <div className="border-b border-neutral-900 pb-6">
                    <div>
                      <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("apiKey")}</p>
                      <p className="text-xs text-neutral-600 mb-4">{t("apiDesc")}</p>
                      
                      <button
                        onClick={testApiKey}
                        disabled={apiTesting}
                        className="bg-white text-black px-6 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {apiTesting ? t("testingBtn") : t("testBtn")}
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
                      <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("baseUrl")}</p>
                      <p className="text-xs text-neutral-600 mb-4">{t("baseUrlDesc")}</p>
                      
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
                          {baseUrlSaving ? t("saving") : t("save")}
                        </button>
                      </div>

                      {baseUrlSaved && (
                        <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ {t("saved")}</p>
                      )}
                      
                      <div className="mt-4 space-y-2 text-xs text-neutral-600">
                        <p className="font-medium text-neutral-500">{t("commonProviders")}</p>
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


                </div>
              </div>
            )}

            {/* Library Section */}
            {activeSection === "library" && (
              <div className="space-y-8">
                <div>
                  <h2 className="text-2xl font-bold uppercase tracking-tight mb-2">{t("library")}</h2>
                  <p className="text-sm text-neutral-500 mb-8">{t("libraryDesc")}</p>
                </div>

                <div className="space-y-6">
                  <div className="border-b border-neutral-900 pb-6">
                    <div>
                      <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("mediaDir")}</p>
                      <p className="text-xs text-neutral-600 mb-4">{t("mediaDirDesc")}</p>
                      
                      <div className="flex gap-3">
                        <input
                          type="text"
                          value={mediaDir}
                          onChange={(e) => setMediaDir(e.target.value)}
                          placeholder="/path/to/movies"
                          className="flex-1 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-sm placeholder:text-neutral-600 hover:border-neutral-600 focus:border-white focus:outline-none"
                        />
                        <button
                          onClick={() => setFileBrowserOpen(true)}
                          className="bg-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-700 transition-colors"
                        >
                          {t("browse")}
                        </button>
                        <button
                          onClick={handleMediaDirChange}
                          disabled={mediaDirSaving}
                          className="bg-white text-black px-6 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {mediaDirSaving ? t("saving") : t("save")}
                        </button>
                      </div>

                      {/* File Browser Modal */}
                      <FileBrowser
                        isOpen={fileBrowserOpen}
                        initialPath={mediaDir}
                        onSelect={(path) => {
                          setMediaDir(path);
                          setFileBrowserOpen(false);
                        }}
                        onCancel={() => setFileBrowserOpen(false)}
                      />

                      {mediaDirSaved && (
                        <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ {t("saved")}</p>
                      )}
                      
                      <div className="mt-4 space-y-2 text-xs text-neutral-600">
                        <p className="font-medium text-neutral-500">{t("note")}</p>
                        <p>{t("noteDocker")}</p>
                        <p className="font-semibold text-neutral-500">{t("noteRestart")}</p>
                      </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between">
                        <div>
                            <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("manualScan")}</p>
                            <p className="text-xs text-neutral-600">{t("manualScanDesc")}</p>
                        </div>
                        <div className="flex items-center gap-4">
                            {scanMessage && (
                                <span className={`text-xs uppercase tracking-widest ${
                                    scanMessage.includes("Failed") || scanMessage.includes("error") 
                                    ? "text-red-500" 
                                    : "text-green-500"
                                }`}>
                                    {scanMessage}
                                </span>
                            )}
                            <button
                                onClick={handleScanLibrary}
                                disabled={isScanning}
                                className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isScanning ? (
                                    <>
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                        {t("scanning")}
                                    </>
                                ) : (
                                    t("scanNow")
                                )}
                            </button>
                        </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1 flex items-center gap-2">
                          Librarian Agent <span className="text-[10px] bg-white text-black px-1.5 py-0.5 tracking-widest font-bold">AI</span>
                        </p>
                        <p className="text-xs text-neutral-600">Summon the agent to autonomously organize the inbox via reasoning.</p>
                      </div>
                      <div className="text-neutral-600 text-xs uppercase">
                        <button
                            onClick={() => setTerminalOpen(true)}
                            className="bg-neutral-900 border border-neutral-800 text-white px-6 py-3 text-xs font-medium uppercase tracking-widest hover:border-neutral-600 transition-colors"
                        >
                            Open Console
                        </button>
                      </div>
                    </div>
                  </div>
                  
                  <LibrarianTerminal isOpen={terminalOpen} onClose={() => setTerminalOpen(false)} />

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
