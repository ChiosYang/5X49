import { mutate } from "swr";

export const EXPLORE_REFRESH_KEY = "explore:read-revisions";
export const initialExploreRefresh = { revision: 0, acknowledged: {} as Record<string, number> };

// Only successful writes publish a receipt. It survives unmount/Back and contains
// no profile data. Each cached Explore address must acknowledge its own fresh read.
export function notifyExploreWrite() {
  void mutate(EXPLORE_REFRESH_KEY, (current: typeof initialExploreRefresh | undefined) => ({
    ...(current ?? initialExploreRefresh), revision: (current?.revision ?? 0) + 1,
  }), { revalidate: false }).catch(() => {});
}
