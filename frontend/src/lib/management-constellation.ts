import type {
  LibraryFilmSummary,
  MissingLibraryItemSummary,
  OrganizationCandidate,
  WorkflowRunView,
} from "@/types/movie";

export type ManagementNodeState =
  | "healthy"
  | "idle"
  | "running"
  | "attention"
  | "failed"
  | "unavailable";

export type ManagementNodeKind =
  | "library"
  | "service"
  | "cluster"
  | "film"
  | "file"
  | "missing";

export type ManagementNodeId =
  | "library"
  | "watcher"
  | "sync"
  | "metadata"
  | "scores"
  | "organizer"
  | "metadata-review"
  | "organization-review"
  | "missing-items"
  | `review:${string}`
  | `organization:${string}`
  | `missing:${string}`;

export interface ManagementNode {
  id: ManagementNodeId;
  kind: ManagementNodeKind;
  label: string;
  detail: string;
  state: ManagementNodeState;
  x: number;
  y: number;
  parentId?: ManagementNodeId;
  count?: number;
  entityId?: string;
}

export interface ManagementEdge {
  id: string;
  from: ManagementNodeId;
  to: ManagementNodeId;
  state: ManagementNodeState;
}

export type ManagementActionId =
  | "scan"
  | "scrape-metadata"
  | "refresh-scores"
  | "review-metadata"
  | "organize-files"
  | "cleanup-missing"
  | "open-settings"
  | "open-activity"
  | "clear-data";

export type ManagementActionDisabledReason =
  | "running"
  | "tmdb-unconfigured"
  | "empty"
  | null;

export interface ManagementActionDefinition {
  id: ManagementActionId;
  nodeIds: ManagementNodeId[];
  danger: boolean;
  disabledReason: ManagementActionDisabledReason;
  destination: string | null;
}

export interface ManagementServiceStatus {
  state?: string;
  error?: string | null;
  detail?: string | null;
}

export interface ManagementConstellationInputs {
  films: LibraryFilmSummary[];
  libraryAvailable?: boolean;
  organizationCandidates: OrganizationCandidate[];
  missingItems: MissingLibraryItemSummary[];
  workflows: WorkflowRunView[];
  tmdbConfigured: boolean;
  watcher: ManagementServiceStatus & { running?: boolean; configured?: boolean };
  sync: ManagementServiceStatus;
  metadata: ManagementServiceStatus;
  scores: ManagementServiceStatus;
  organizer: ManagementServiceStatus;
  childLimit?: number;
}

export interface ManagementConstellationModel {
  nodes: ManagementNode[];
  edges: ManagementEdge[];
  actions: ManagementActionDefinition[];
  attentionCount: number;
  reviewFilms: LibraryFilmSummary[];
  organizationCandidates: OrganizationCandidate[];
  missingItems: MissingLibraryItemSummary[];
}

const SYSTEM_POSITIONS: Record<
  "library" | "watcher" | "sync" | "metadata" | "scores" | "organizer",
  { x: number; y: number }
> = {
  library: { x: 50, y: 52 },
  watcher: { x: 16, y: 24 },
  sync: { x: 20, y: 70 },
  metadata: { x: 50, y: 14 },
  scores: { x: 83, y: 25 },
  organizer: { x: 81, y: 70 },
};

const CLUSTER_POSITIONS = {
  "metadata-review": { x: 48, y: 33 },
  "organization-review": { x: 66, y: 78 },
  "missing-items": { x: 34, y: 79 },
} as const;

const WORKFLOW_SERVICE: Record<string, ManagementNodeId> = {
  "library.reconcile": "sync",
  "library.scan_folder": "sync",
  "library.mark_path_missing": "sync",
  "metadata.scrape_library": "metadata",
  "organizer.organize_root": "organizer",
  "organizer.confirm_root_video": "organizer",
  "external_scores.refresh_library": "scores",
  "external_scores.refresh_film": "scores",
};

const stateRank: Record<ManagementNodeState, number> = {
  healthy: 0,
  idle: 1,
  unavailable: 2,
  attention: 3,
  running: 4,
  failed: 5,
};

function strongestState(...states: ManagementNodeState[]): ManagementNodeState {
  return states.reduce((strongest, state) => (
    stateRank[state] > stateRank[strongest] ? state : strongest
  ), "healthy");
}

function rawServiceState(status: ManagementServiceStatus): ManagementNodeState {
  if (status.error || status.state === "failed" || status.state === "error") return "failed";
  if (status.state === "running") return "running";
  if (!status.state) return "unavailable";
  return status.state === "idle" ? "idle" : "healthy";
}

function workflowState(
  nodeId: ManagementNodeId,
  workflows: WorkflowRunView[],
): ManagementNodeState {
  const relevant = workflows.filter((workflow) => WORKFLOW_SERVICE[workflow.type] === nodeId);
  if (relevant.some((workflow) => workflow.status === "failed")) return "failed";
  if (relevant.some((workflow) => workflow.status === "running" || workflow.status === "queued")) {
    return "running";
  }
  return "healthy";
}

function serviceNode(
  id: "watcher" | "sync" | "metadata" | "scores" | "organizer",
  label: string,
  detail: string,
  state: ManagementNodeState,
): ManagementNode {
  return { id, kind: "service", label, detail, state, ...SYSTEM_POSITIONS[id] };
}

function radialChildren(
  parent: ManagementNode,
  children: Array<Omit<ManagementNode, "x" | "y" | "parentId">>,
): ManagementNode[] {
  const count = Math.max(children.length, 1);
  const radiusX = 22;
  const radiusY = 18;
  return children.map((child, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / count;
    return {
      ...child,
      parentId: parent.id,
      x: Math.max(7, Math.min(93, parent.x + Math.cos(angle) * radiusX)),
      y: Math.max(10, Math.min(90, parent.y + Math.sin(angle) * radiusY)),
    };
  });
}

function metadataReviews(films: LibraryFilmSummary[]) {
  return films
    .filter((film) => film.primary_item.metadata.scrape_status === "needs_review")
    .sort((left, right) => (
      Number(Boolean(right.primary_item.metadata.scrape_error))
      - Number(Boolean(left.primary_item.metadata.scrape_error))
      || left.title.localeCompare(right.title)
      || (left.year ?? 0) - (right.year ?? 0)
      || left.id.localeCompare(right.id)
    ));
}

function organizationQueue(items: OrganizationCandidate[]) {
  return [...items].sort((left, right) => (
    Number(right.stable) - Number(left.stable)
    || left.mtime - right.mtime
    || left.parsed_title.localeCompare(right.parsed_title)
    || (left.parsed_year ?? 0) - (right.parsed_year ?? 0)
    || left.source_path.localeCompare(right.source_path)
  ));
}

function missingQueue(items: MissingLibraryItemSummary[]) {
  return [...items].sort((left, right) => (
    (left.missing_since ?? "").localeCompare(right.missing_since ?? "")
    || left.title.localeCompare(right.title)
    || left.library_item_id.localeCompare(right.library_item_id)
  ));
}

function edge(from: ManagementNode, to: ManagementNode): ManagementEdge {
  return {
    id: `${from.id}->${to.id}`,
    from: from.id,
    to: to.id,
    state: strongestState(from.state, to.state),
  };
}

export function buildManagementConstellation(
  inputs: ManagementConstellationInputs,
): ManagementConstellationModel {
  const childLimit = Math.max(1, inputs.childLimit ?? 8);
  const reviews = metadataReviews(inputs.films);
  const organization = organizationQueue(inputs.organizationCandidates);
  const missing = missingQueue(inputs.missingItems);

  const library: ManagementNode = {
    id: "library",
    kind: "library",
    label: "library",
    detail: String(inputs.films.length),
    state: inputs.libraryAvailable === false ? "unavailable" : "healthy",
    count: inputs.films.length,
    ...SYSTEM_POSITIONS.library,
  };
  const watcherBase: ManagementNodeState = inputs.watcher.error
    ? "failed"
    : !inputs.watcher.configured
      ? "unavailable"
      : inputs.watcher.running
        ? "healthy"
        : "idle";
  const watcher = serviceNode(
    "watcher",
    "watcher",
    inputs.watcher.detail ?? "",
    watcherBase,
  );
  const sync = serviceNode(
    "sync",
    "sync",
    inputs.sync.detail ?? "",
    strongestState(
      rawServiceState(inputs.sync),
      workflowState("sync", inputs.workflows),
      missing.length > 0 ? "attention" : "healthy",
    ),
  );
  const metadataRuntimeState = strongestState(
    rawServiceState(inputs.metadata),
    workflowState("metadata", inputs.workflows),
    reviews.length > 0 ? "attention" : "healthy",
  );
  const metadata = serviceNode(
    "metadata",
    "metadata",
    inputs.metadata.detail ?? "",
    !inputs.tmdbConfigured && metadataRuntimeState !== "failed"
      ? "unavailable"
      : metadataRuntimeState,
  );
  const scores = serviceNode(
    "scores",
    "scores",
    inputs.scores.detail ?? "",
    strongestState(rawServiceState(inputs.scores), workflowState("scores", inputs.workflows)),
  );
  const organizer = serviceNode(
    "organizer",
    "organizer",
    inputs.organizer.detail ?? "",
    strongestState(
      rawServiceState(inputs.organizer),
      workflowState("organizer", inputs.workflows),
      organization.length > 0 ? "attention" : "healthy",
    ),
  );

  const nodes: ManagementNode[] = [library, watcher, sync, metadata, scores, organizer];
  const edges: ManagementEdge[] = [watcher, sync, metadata, scores, organizer]
    .map((node) => edge(library, node));

  const clusters: ManagementNode[] = [];
  if (reviews.length > 0) {
    clusters.push({
      id: "metadata-review",
      kind: "cluster",
      label: "metadata-review",
      detail: String(reviews.length),
      state: "attention",
      count: reviews.length,
      parentId: "metadata",
      ...CLUSTER_POSITIONS["metadata-review"],
    });
  }
  if (organization.length > 0) {
    clusters.push({
      id: "organization-review",
      kind: "cluster",
      label: "organization-review",
      detail: String(organization.length),
      state: organization.some((item) => item.stable) ? "attention" : "idle",
      count: organization.length,
      parentId: "organizer",
      ...CLUSTER_POSITIONS["organization-review"],
    });
  }
  if (missing.length > 0) {
    clusters.push({
      id: "missing-items",
      kind: "cluster",
      label: "missing-items",
      detail: String(missing.length),
      state: "attention",
      count: missing.length,
      parentId: "sync",
      ...CLUSTER_POSITIONS["missing-items"],
    });
  }
  clusters.forEach((cluster) => {
    nodes.push(cluster);
    const parent = nodes.find((node) => node.id === cluster.parentId);
    if (parent) edges.push(edge(parent, cluster));
  });

  const reviewCluster = clusters.find((node) => node.id === "metadata-review");
  if (reviewCluster) {
    const children = radialChildren(
      reviewCluster,
      reviews.slice(0, childLimit).map((film) => ({
        id: `review:${film.id}` as const,
        kind: "film" as const,
        label: film.title,
        detail: film.year ? String(film.year) : "",
        state: film.primary_item.metadata.scrape_error ? "failed" as const : "attention" as const,
        entityId: film.id,
      })),
    );
    nodes.push(...children);
    edges.push(...children.map((child) => edge(reviewCluster, child)));
  }

  const organizationCluster = clusters.find((node) => node.id === "organization-review");
  if (organizationCluster) {
    const children = radialChildren(
      organizationCluster,
      organization.slice(0, childLimit).map((item) => ({
        id: `organization:${item.source_path}` as const,
        kind: "file" as const,
        label: item.parsed_title || item.filename,
        detail: item.parsed_year ? String(item.parsed_year) : item.filename,
        state: item.stable ? "attention" as const : "idle" as const,
        entityId: item.source_path,
      })),
    );
    nodes.push(...children);
    edges.push(...children.map((child) => edge(organizationCluster, child)));
  }

  const missingCluster = clusters.find((node) => node.id === "missing-items");
  if (missingCluster) {
    const children = radialChildren(
      missingCluster,
      missing.slice(0, childLimit).map((item) => ({
        id: `missing:${item.library_item_id}` as const,
        kind: "missing" as const,
        label: item.title,
        detail: item.year ? String(item.year) : "",
        state: "attention" as const,
        entityId: item.library_item_id,
      })),
    );
    nodes.push(...children);
    edges.push(...children.map((child) => edge(missingCluster, child)));
  }

  const actions: ManagementActionDefinition[] = [
    { id: "scan", nodeIds: ["library", "sync"], danger: false, disabledReason: inputs.sync.state === "running" ? "running" : null, destination: null },
    { id: "scrape-metadata", nodeIds: ["metadata"], danger: false, disabledReason: !inputs.tmdbConfigured ? "tmdb-unconfigured" : inputs.metadata.state === "running" ? "running" : null, destination: null },
    { id: "refresh-scores", nodeIds: ["scores"], danger: false, disabledReason: inputs.scores.state === "running" ? "running" : null, destination: null },
    { id: "review-metadata", nodeIds: ["metadata", "metadata-review"], danger: false, disabledReason: reviews.length === 0 ? "empty" : null, destination: "/library?view=metadata" },
    { id: "organize-files", nodeIds: ["organizer", "organization-review"], danger: false, disabledReason: organization.length === 0 ? "empty" : null, destination: "/library?view=inbox" },
    { id: "cleanup-missing", nodeIds: ["sync", "missing-items"], danger: true, disabledReason: missing.length === 0 ? "empty" : null, destination: "/library?view=offline" },
    { id: "open-settings", nodeIds: ["watcher", "library"], danger: false, disabledReason: null, destination: "/settings?section=library" },
    { id: "open-activity", nodeIds: ["library"], danger: false, disabledReason: null, destination: "/library/activity" },
    { id: "clear-data", nodeIds: ["library"], danger: true, disabledReason: null, destination: "/settings?section=library#danger-zone" },
  ];

  return {
    nodes,
    edges,
    actions,
    attentionCount: reviews.length + organization.length + missing.length,
    reviewFilms: reviews,
    organizationCandidates: organization,
    missingItems: missing,
  };
}
