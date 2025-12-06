import type { ReactNode } from "react";
import { PersistentLayoutShell } from "@/components/layout/PersistentLayoutShell";

export default function WorkspaceLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <PersistentLayoutShell>{children}</PersistentLayoutShell>;
}

