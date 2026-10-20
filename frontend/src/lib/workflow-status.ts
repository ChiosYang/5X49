import type { WorkflowRunView } from "@/types/movie";

// These actors inspect media using the configured roots; refresh_item delegates to scan_folder.
export function isLibraryScanWorkflow(type: string) {
  return ["library.reconcile", "library.scan_folder", "library.refresh_item"].includes(type);
}

export function retainRecentWorkflows(workflows: WorkflowRunView[], limit = 8) {
  const ordered = [...workflows].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return ordered.filter((workflow, index) => index < limit || workflow.status === "queued" || workflow.status === "running");
}
