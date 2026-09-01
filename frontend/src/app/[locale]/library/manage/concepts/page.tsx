import type { Metadata } from "next";

import ManagementInteractionLab from "./ManagementInteractionLab";

export const metadata: Metadata = {
  title: "Management Interaction Lab · 5X49",
  description: "Three disposable interaction prototypes for the 5X49 management experience.",
};

export default function ManagementInteractionLabPage() {
  return <ManagementInteractionLab />;
}
