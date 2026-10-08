import type { WorkflowRunView } from "@/types/movie";

export function retainRecentWorkflows(workflows: WorkflowRunView[], limit = 8) {
  const ordered = [...workflows].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return ordered.filter((workflow, index) => index < limit || workflow.status === "queued" || workflow.status === "running");
}
