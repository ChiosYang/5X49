import type { Metadata } from "next";

import VisualInteractionLab from "./VisualInteractionLab";

export const metadata: Metadata = {
  title: "Management Visual Lab · 5X49",
  description: "Three visually innovative interaction prototypes for 5X49 management.",
};

export default function ManagementVisualConceptsPage() {
  return <VisualInteractionLab />;
}
