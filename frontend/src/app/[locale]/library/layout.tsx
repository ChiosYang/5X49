import type { ReactNode } from "react";

export default function LibraryLayout({
  children,
  detail = null,
}: {
  children: ReactNode;
  detail?: ReactNode;
}) {
  return (
    <>
      {children}
      {detail}
    </>
  );
}
