import LibraryEventsRefresher from "./LibraryEventsRefresher";
import type { ReactNode } from "react";

export default function LibraryLayout({
  children,
  detail,
}: {
  children: ReactNode;
  detail: ReactNode;
}) {
  return (
    <>
      <LibraryEventsRefresher />
      {children}
      {detail}
    </>
  );
}
