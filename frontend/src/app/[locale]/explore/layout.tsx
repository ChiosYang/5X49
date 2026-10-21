import type { ReactNode } from "react";
import DiscoverySearchSession from "./DiscoverySearchSession";

export default function ExploreLayout({ children }: { children: ReactNode }) {
  return <DiscoverySearchSession>{children}</DiscoverySearchSession>;
}
