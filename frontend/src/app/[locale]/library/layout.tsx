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
      {children}
      {detail}
    </>
  );
}
