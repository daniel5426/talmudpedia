'use client';

import { LayoutShell } from '@/components/layout/LayoutShell';
import { usePathname } from 'next/navigation';
import { ChatPane } from '@/components/layout/ChatPane';
import { DocumentSearchPane } from '@/components/layout/DocumentSearchPane';

interface PersistentLayoutShellProps {
  children?: React.ReactNode;
}

export function PersistentLayoutShell({ children }: PersistentLayoutShellProps) {
  const pathname = usePathname();
  
  // Only use persistent layout for main app routes
  // Admin, login, signup routes should render their own content
  const isMainAppRoute = pathname === '/' || pathname === '/document-search';
  
  if (!isMainAppRoute) {
    // For admin, login, signup, etc., render the page content directly
    return <>{children}</>;
  }
  
  // Determine which pane to show based on the route
  const getMainContent = () => {
    if (pathname === '/document-search') {
      return <DocumentSearchPane />;
    }
    // Default to ChatPane for home
    return <ChatPane />;
  };

  return (
    <main className="h-screen overflow-hidden bg-background">
      <LayoutShell>
        {getMainContent()}
      </LayoutShell>
    </main>
  );
}
