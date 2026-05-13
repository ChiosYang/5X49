"use client";

import { useState, useEffect, useMemo } from "react";
import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { useRouter, usePathname } from "@/i18n/routing";
import Providers from "@/components/Providers";

import FileBrowser from "@/components/FileBrowser";
import LibrarianTerminal from "@/components/LibrarianTerminal";
import {
  useModelSettings,
  useBaseUrl,
  useMediaDir,
  useLanguageSetting,
  useUpdateModel,
  useUpdateBaseUrl,
  useUpdateMediaDir,
  useUpdateLanguage,
  useUpdateLibraryWatch,
  useTestApiKey,
  useScanLibrary,
  useReconcileLibrary,
  useScrapeLibrary,
  useLibraryScrapeStatus,
  useCleanupMissingMovies,
  useAutoOrganizeRootSetting,
  useUpdateAutoOrganizeRoot,
  useOrganizeRootVideos,
  useLibraryOrganizeStatus,
  useLibrarySyncStatus,
  useLibraryWatchSetting,
  useTmdbSettings,
  useUpdateTmdbKey,
  useTestTmdbKey,
} from "@/hooks/useSettings";

type SettingSection = "appearance" | "display" | "analysis" | "library";

function SettingsContent() {
  const t = useTranslations("Settings");
  const router = useRouter();
  const pathname = usePathname();

  // ---- Server State (SWR) ----
  const { data: modelData } = useModelSettings();
  const { data: baseUrlData } = useBaseUrl();
  const { data: mediaDirData } = useMediaDir();
  const { data: langData } = useLanguageSetting();
  const { data: libraryWatchData } = useLibraryWatchSetting();
  const { data: autoOrganizeRootData } = useAutoOrganizeRootSetting();
  const { data: tmdbData } = useTmdbSettings();
  const { data: syncStatus } = useLibrarySyncStatus();
  const { data: scrapeStatus } = useLibraryScrapeStatus();
  const { data: organizeStatus } = useLibraryOrganizeStatus();

  const { trigger: updateModel, isMutating: modelSaving, data: modelSaveResult, reset: resetModelSave } = useUpdateModel();
  const { trigger: updateBaseUrl, isMutating: baseUrlSaving, data: baseUrlSaveResult, reset: resetBaseUrlSave } = useUpdateBaseUrl();
  const { trigger: updateMediaDir, isMutating: mediaDirSaving, data: mediaDirSaveResult, reset: resetMediaDirSave } = useUpdateMediaDir();
  const { trigger: updateLanguage, isMutating: languageSaving } = useUpdateLanguage();
  const { trigger: updateLibraryWatch, isMutating: watchSaving } = useUpdateLibraryWatch();
  const { trigger: updateAutoOrganizeRoot, isMutating: autoOrganizeSaving } = useUpdateAutoOrganizeRoot();
  const { trigger: updateTmdbKey, isMutating: tmdbSaving, data: tmdbSaveResult, error: tmdbSaveError, reset: resetTmdbSave } = useUpdateTmdbKey();
  const { trigger: testTmdbKey, data: tmdbTestResult, isMutating: tmdbTesting, error: tmdbTestError } = useTestTmdbKey();
  const { trigger: testApi, data: apiTestResult, isMutating: apiTesting } = useTestApiKey();
  const { trigger: scanLibrary, isMutating: isScanning, data: scanResult, error: scanError } = useScanLibrary();
  const { trigger: reconcileLibrary, isMutating: isReconciling, data: reconcileResult, error: reconcileError } = useReconcileLibrary();
  const { trigger: scrapeLibrary, isMutating: isScrapingMetadata, data: scrapeResult, error: scrapeError } = useScrapeLibrary();
  const { trigger: organizeRootVideos, isMutating: isOrganizingRoot, data: organizeResult, error: organizeError } = useOrganizeRootVideos();
  const { trigger: cleanupMissing, isMutating: isCleaningMissing, data: cleanupResult, error: cleanupError } = useCleanupMissingMovies();

  // ---- Client State (UI only) ----
  const [activeSection, setActiveSection] = useState<SettingSection>("appearance");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [modelSearch, setModelSearch] = useState("");
  const [fileBrowserOpen, setFileBrowserOpen] = useState(false);
  const [terminalOpen, setTerminalOpen] = useState(false);

  // Form edit state: local drafts for user editing before save.
  const [baseUrlDraft, setBaseUrlInput] = useState<string>();
  const [mediaDirDraft, setMediaDirInput] = useState<string>();
  const [tmdbKeyDraft, setTmdbKeyDraft] = useState("");

  // Auto-clear save success indicators
  useEffect(() => {
    if (modelSaveResult) {
      const timer = setTimeout(() => resetModelSave(), 3000);
      return () => clearTimeout(timer);
    }
  }, [modelSaveResult, resetModelSave]);

  useEffect(() => {
    if (baseUrlSaveResult) {
      const timer = setTimeout(() => resetBaseUrlSave(), 3000);
      return () => clearTimeout(timer);
    }
  }, [baseUrlSaveResult, resetBaseUrlSave]);

  useEffect(() => {
    if (mediaDirSaveResult) {
      const timer = setTimeout(() => resetMediaDirSave(), 3000);
      return () => clearTimeout(timer);
    }
  }, [mediaDirSaveResult, resetMediaDirSave]);

  useEffect(() => {
    if (tmdbSaveResult) {
      const timer = setTimeout(() => resetTmdbSave(), 3000);
      return () => clearTimeout(timer);
    }
  }, [tmdbSaveResult, resetTmdbSave]);

  // Derived values
  const currentModel = modelData?.current_model || "";
  const availableModels = useMemo(
    () => modelData?.available_models || [],
    [modelData?.available_models]
  );
  const baseUrlInput = baseUrlDraft ?? baseUrlData?.base_url ?? "";
  const mediaDirInput = mediaDirDraft ?? mediaDirData?.media_dir ?? "";
  const tmdbStatus = tmdbSaveResult ?? tmdbData;
  const tmdbSourceLabel = tmdbStatus?.source === "environment"
    ? t("tmdbSourceEnvironment")
    : tmdbStatus?.source === "settings"
      ? t("tmdbSourceSettings")
      : t("tmdbSourceMissing");
  const tmdbCanSave = tmdbStatus?.source !== "environment";
  const scrapeBlocked = tmdbStatus?.configured === false;

  const filteredModels = useMemo(() => {
    if (!modelSearch.trim()) return availableModels;
    const search = modelSearch.toLowerCase();
    return availableModels.filter((model: string) =>
      model.toLowerCase().includes(search)
    );
  }, [availableModels, modelSearch]);

  // ---- Handlers ----
  const handleModelChange = async (newModel: string) => {
    await updateModel(newModel);
  };

  const handleBaseUrlChange = async () => {
    await updateBaseUrl(baseUrlInput);
  };

  const handleMediaDirChange = async () => {
    await updateMediaDir(mediaDirInput);
  };

  const handleLanguageChange = async (lang: "zh" | "en") => {
    const currentLang = langData?.language;
    if (lang === currentLang) return;
    await updateLanguage(lang);
    router.replace({ pathname }, { locale: lang });
  };

  const handleScanLibrary = async () => {
    await scanLibrary();
  };

  const handleReconcileLibrary = async () => {
    await reconcileLibrary();
  };

  const handleScrapeLibrary = async () => {
    await scrapeLibrary();
  };

  const handleOrganizeRootVideos = async () => {
    await organizeRootVideos();
  };

  const handleCleanupMissing = async () => {
    await cleanupMissing();
  };

  const handleLibraryWatchChange = async () => {
    await updateLibraryWatch(!libraryWatchData?.watch_library);
  };

  const handleAutoOrganizeRootChange = async () => {
    await updateAutoOrganizeRoot(!autoOrganizeRootData?.auto_organize_root_videos);
  };

  const handleTmdbKeySave = async () => {
    await updateTmdbKey(tmdbKeyDraft);
    setTmdbKeyDraft("");
  };

  const handleTmdbKeyTest = async () => {
    await testTmdbKey();
  };

  // Scan message derived from mutation state
  const scanMessage = scanResult
    ? "Scan started in background"
    : scanError
      ? "Failed to start scan"
      : "";
  const reconcileMessage = reconcileResult
    ? `Scanned ${reconcileResult.scanned ?? 0}, missing ${reconcileResult.missing ?? 0}`
    : reconcileError
      ? "Failed to reconcile"
      : "";
  const scrapeMessage = scrapeResult
    ? "Metadata scrape started"
    : scrapeError
      ? "Failed to start metadata scrape"
      : scrapeBlocked
        ? t("tmdbRequiredForScrape")
      : scrapeStatus?.last_result
        ? `Scraped ${scrapeStatus.last_result.succeeded ?? 0}, review ${scrapeStatus.last_result.needs_review ?? 0}`
        : "";
  const organizeMessage = organizeResult
    ? "Root organization started"
    : organizeError
      ? "Failed to organize root videos"
      : organizeStatus?.last_result
        ? `Organized ${organizeStatus.last_result.organized ?? 0}, review ${organizeStatus.last_result.needs_review ?? 0}`
        : "";
  const cleanupMessage = cleanupResult
    ? `Deleted ${cleanupResult.deleted ?? 0}`
    : cleanupError
      ? "Failed to clean missing"
      : "";

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
                              langData?.language === "zh" ? "bg-white text-black" : "text-neutral-500 hover:text-white"
                            }`}
                          >
                            ZH
                          </button>
                          <button
                            onClick={() => handleLanguageChange("en")}
                            disabled={languageSaving}
                            className={`px-4 py-2 text-xs font-medium uppercase tracking-widest transition-colors ${
                              langData?.language === "en" ? "bg-white text-black" : "text-neutral-500 hover:text-white"
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
                        
                        {modelSaveResult && (
                          <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ Saved</p>
                        )}
                        {modelSaving && (
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
                        onClick={() => testApi()}
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
                          value={baseUrlInput}
                          onChange={(e) => setBaseUrlInput(e.target.value)}
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

                      {baseUrlSaveResult && (
                        <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ {t("saved")}</p>
                      )}
                      
                      <div className="mt-4 space-y-2 text-xs text-neutral-600">
                        <p className="font-medium text-neutral-500">{t("commonProviders")}</p>
                        <button
                          onClick={() => setBaseUrlInput("https://openrouter.ai/api/v1")}
                          className="block hover:text-white transition-colors"
                        >
                          • OpenRouter: https://openrouter.ai/api/v1
                        </button>
                        <button
                          onClick={() => setBaseUrlInput("https://api.openai.com/v1")}
                          className="block hover:text-white transition-colors"
                        >
                          • OpenAI: https://api.openai.com/v1
                        </button>
                        <button
                          onClick={() => setBaseUrlInput("https://api.anthropic.com/v1")}
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
                          value={mediaDirInput}
                          onChange={(e) => setMediaDirInput(e.target.value)}
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
                      {fileBrowserOpen && (
                        <FileBrowser
                          isOpen={fileBrowserOpen}
                          initialPath={mediaDirInput}
                          onSelect={(path) => {
                            setMediaDirInput(path);
                            setFileBrowserOpen(false);
                          }}
                          onCancel={() => setFileBrowserOpen(false)}
                        />
                      )}

                      {mediaDirSaveResult && (
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
                    <div>
                      <div className="flex items-start justify-between gap-4 mb-4">
                        <div>
                          <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("tmdbApiKey")}</p>
                          <p className="text-xs text-neutral-600">{t("tmdbApiKeyDesc")}</p>
                        </div>
                        <span className={`shrink-0 text-xs uppercase tracking-widest ${
                          tmdbStatus?.configured ? "text-green-500" : "text-neutral-600"
                        }`}>
                          {tmdbSourceLabel}
                        </span>
                      </div>

                      <div className="flex flex-col gap-3 md:flex-row">
                        <input
                          type="password"
                          value={tmdbKeyDraft}
                          onChange={(e) => setTmdbKeyDraft(e.target.value)}
                          disabled={!tmdbCanSave}
                          placeholder={tmdbCanSave ? t("tmdbApiKeyPlaceholder") : t("tmdbApiKeyEnvironment")}
                          className="flex-1 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-sm placeholder:text-neutral-600 hover:border-neutral-600 focus:border-white focus:outline-none disabled:opacity-50"
                        />
                        <button
                          type="button"
                          onClick={handleTmdbKeySave}
                          disabled={!tmdbCanSave || tmdbSaving}
                          className="bg-white text-black px-6 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {tmdbSaving ? t("saving") : t("save")}
                        </button>
                        <button
                          type="button"
                          onClick={handleTmdbKeyTest}
                          disabled={tmdbTesting || !tmdbStatus?.configured}
                          className="bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {tmdbTesting ? t("testingBtn") : t("tmdbTestBtn")}
                        </button>
                      </div>

                      {tmdbSaveResult && (
                        <p className="text-xs text-green-500 mt-2 uppercase tracking-widest">✓ {t("saved")}</p>
                      )}
                      {tmdbSaveError && (
                        <p className="text-xs text-red-500 mt-2">{tmdbSaveError instanceof Error ? tmdbSaveError.message : t("tmdbSaveFailed")}</p>
                      )}
                      {tmdbTestResult && (
                        <p className={`text-xs mt-2 ${
                          tmdbTestResult.status === "success" ? "text-green-500" : "text-red-500"
                        }`}>
                          {tmdbTestResult.message}
                        </p>
                      )}
                      {tmdbTestError && (
                        <p className="text-xs text-red-500 mt-2">{tmdbTestError instanceof Error ? tmdbTestError.message : t("tmdbTestFailed")}</p>
                      )}
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
                                    scanError 
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
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("reconcileLibrary")}</p>
                        <p className="text-xs text-neutral-600">{t("reconcileLibraryDesc")}</p>
                        {syncStatus?.sync.last_finished_at && (
                          <p className="text-xs text-neutral-700 mt-2">
                            Last sync: {new Date(syncStatus.sync.last_finished_at).toLocaleString()}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-4">
                        {reconcileMessage && (
                          <span className={`text-xs uppercase tracking-widest ${
                            reconcileError ? "text-red-500" : "text-green-500"
                          }`}>
                            {reconcileMessage}
                          </span>
                        )}
                        <button
                          onClick={handleReconcileLibrary}
                          disabled={isReconciling}
                          className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isReconciling ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {t("scanning")}
                            </>
                          ) : (
                            t("reconcileNow")
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("scrapeMetadata")}</p>
                        <p className="text-xs text-neutral-600">{t("scrapeMetadataDesc")}</p>
                        {scrapeStatus?.last_error && (
                          <p className="text-xs text-red-500 mt-2">{scrapeStatus.last_error}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-4">
                        {scrapeMessage && (
                          <span className={`text-xs uppercase tracking-widest ${
                            scrapeError ? "text-red-500" : "text-green-500"
                          }`}>
                            {scrapeMessage}
                          </span>
                        )}
                        <button
                          onClick={handleScrapeLibrary}
                          disabled={isScrapingMetadata || scrapeStatus?.state === "running" || scrapeBlocked}
                          className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isScrapingMetadata || scrapeStatus?.state === "running" ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {t("scraping")}
                            </>
                          ) : (
                            t("scrapeNow")
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("organizeRoot")}</p>
                        <p className="text-xs text-neutral-600">{t("organizeRootDesc")}</p>
                        {organizeStatus?.last_error && (
                          <p className="text-xs text-red-500 mt-2">{organizeStatus.last_error}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-4">
                        {organizeMessage && (
                          <span className={`text-xs uppercase tracking-widest ${
                            organizeError ? "text-red-500" : "text-green-500"
                          }`}>
                            {organizeMessage}
                          </span>
                        )}
                        <button
                          onClick={handleOrganizeRootVideos}
                          disabled={isOrganizingRoot || organizeStatus?.state === "running"}
                          className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isOrganizingRoot || organizeStatus?.state === "running" ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {t("organizing")}
                            </>
                          ) : (
                            t("organizeNow")
                          )}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("cleanupMissing")}</p>
                        <p className="text-xs text-neutral-600">{t("cleanupMissingDesc")}</p>
                      </div>
                      <div className="flex items-center gap-4">
                        {cleanupMessage && (
                          <span className={`text-xs uppercase tracking-widest ${
                            cleanupError ? "text-red-500" : "text-green-500"
                          }`}>
                            {cleanupMessage}
                          </span>
                        )}
                        <button
                          onClick={handleCleanupMissing}
                          disabled={isCleaningMissing}
                          className="flex items-center gap-2 bg-neutral-900 border border-neutral-800 text-white px-4 py-3 text-xs font-medium uppercase tracking-widest hover:bg-neutral-800 hover:border-neutral-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isCleaningMissing ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin" />
                              {t("cleaning")}
                            </>
                          ) : (
                            t("cleanupNow")
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
                    <div className="flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("autoScan")}</p>
                        <p className="text-xs text-neutral-600">{t("autoScanDesc")}</p>
                        {syncStatus?.watcher.last_error && (
                          <p className="text-xs text-red-500 mt-2">{syncStatus.watcher.last_error}</p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={handleLibraryWatchChange}
                        disabled={watchSaving}
                        className={`relative h-7 w-12 shrink-0 border transition-colors ${
                          libraryWatchData?.watch_library
                            ? "bg-white border-white"
                            : "bg-neutral-900 border-neutral-700"
                        } disabled:opacity-50`}
                        aria-label={t("autoScan")}
                      >
                        <span
                          className={`absolute left-1 top-1 h-5 w-5 bg-black transition-transform ${
                            libraryWatchData?.watch_library ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
                  </div>

                  <div className="border-b border-neutral-900 pb-6">
                    <div className="flex items-center justify-between gap-4">
                      <div className="min-w-0">
                        <p className="text-sm font-medium uppercase tracking-widest mb-1">{t("autoOrganizeRoot")}</p>
                        <p className="text-xs text-neutral-600">{t("autoOrganizeRootDesc")}</p>
                      </div>
                      <button
                        type="button"
                        onClick={handleAutoOrganizeRootChange}
                        disabled={autoOrganizeSaving}
                        className={`relative h-7 w-12 shrink-0 border transition-colors ${
                          autoOrganizeRootData?.auto_organize_root_videos
                            ? "bg-white border-white"
                            : "bg-neutral-900 border-neutral-700"
                        } disabled:opacity-50`}
                        aria-label={t("autoOrganizeRoot")}
                      >
                        <span
                          className={`absolute left-1 top-1 h-5 w-5 bg-black transition-transform ${
                            autoOrganizeRootData?.auto_organize_root_videos ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
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

export default function SettingsPage() {
  return (
    <Providers>
      <SettingsContent />
    </Providers>
  );
}
