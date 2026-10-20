import { Suspense } from "react";
import VideoHealthNotice from "@/components/VideoHealthNotice";
import WorkflowRuntimeStatus from "@/components/WorkflowRuntimeStatus";
import NavigationSearch from "./NavigationSearch";

export default function Navigation() {
  return <Suspense><NavigationSearch><VideoHealthNotice /><WorkflowRuntimeStatus /></NavigationSearch></Suspense>;
}
