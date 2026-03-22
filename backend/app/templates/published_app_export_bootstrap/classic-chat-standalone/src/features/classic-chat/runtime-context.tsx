import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type RuntimeUser = {
  id: string;
  email: string;
  full_name?: string;
  avatar?: string | null;
};

type RuntimeContextValue = {
  authClient: {
    logout: () => Promise<void>;
  };
  user: RuntimeUser | null;
  isLoadingUser: boolean;
  refreshUser: () => Promise<void>;
};

const RuntimeContext = createContext<RuntimeContextValue | null>(null);

async function readSession(): Promise<RuntimeUser | null> {
  const response = await fetch("/api/session", {
    method: "GET",
    credentials: "same-origin",
  });
  if (!response.ok) {
    throw new Error("Failed to load local session.");
  }
  const payload = await response.json() as { user?: RuntimeUser | null };
  return payload.user || null;
}

export function RuntimeProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<RuntimeUser | null>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(true);

  const refreshUser = useCallback(async () => {
    setIsLoadingUser(true);
    try {
      setUser(await readSession());
    } catch (error) {
      console.warn("Failed to refresh local session:", error);
      setUser(null);
    } finally {
      setIsLoadingUser(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const authClient = useMemo(
    () => ({
      async logout() {
        await fetch("/api/session", {
          method: "DELETE",
          credentials: "same-origin",
        });
      },
    }),
    [],
  );

  return (
    <RuntimeContext.Provider value={{ authClient, user, isLoadingUser, refreshUser }}>
      {children}
    </RuntimeContext.Provider>
  );
}

export function useRuntime() {
  const context = useContext(RuntimeContext);
  if (!context) {
    throw new Error("useRuntime must be used within a RuntimeProvider");
  }
  return context;
}
