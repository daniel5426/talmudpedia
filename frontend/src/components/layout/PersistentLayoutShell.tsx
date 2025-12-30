'use client';

import { LayoutShell } from '@/components/layout/LayoutShell';

interface PersistentLayoutShellProps {
  children?: React.ReactNode;
}

export function PersistentLayoutShell({ children }: PersistentLayoutShellProps) {
  return (
    <main className="h-full overflow-hidden bg-background">
      <LayoutShell>
        {children}
      </LayoutShell>
    </main>
  );
}
