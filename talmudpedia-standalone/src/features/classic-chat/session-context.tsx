import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useState,
} from "react";

export type SessionInfo = {
  userId: string;
  displayName: string;
  selectedClientId: string | null;
  availableClients: Array<{
    id: string;
    name: string;
    sector: string;
    baseCurrency: string;
  }>;
};

type SessionContextValue = {
  session: SessionInfo | null;
  isLoading: boolean;
  resetSession: () => Promise<void>;
  setSelectedClientId: (clientId: string) => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

async function fetchSession(): Promise<SessionInfo> {
  const response = await fetch("/api/session", { credentials: "same-origin" });
  if (!response.ok) {
    throw new Error("Failed to fetch local session.");
  }
  return (await response.json()) as SessionInfo;
}

async function updateSelectedClient(clientId: string): Promise<SessionInfo> {
  const response = await fetch("/api/session/client", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ clientId }),
  });
  if (!response.ok) {
    throw new Error("Failed to update selected client.");
  }
  return (await response.json()) as SessionInfo;
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const nextSession = await fetchSession();
        if (!cancelled) {
          setSession(nextSession);
        }
      } catch (error) {
        if (!cancelled) {
          console.error(error);
          setSession(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const resetSession = async () => {
    await fetch("/api/session", {
      method: "DELETE",
      credentials: "same-origin",
    });
    setIsLoading(true);
    const nextSession = await fetchSession();
    setSession(nextSession);
    setIsLoading(false);
  };

  const setSelectedClientId = async (clientId: string) => {
    const nextSession = await updateSelectedClient(clientId);
    setSession(nextSession);
  };

  return (
    <SessionContext.Provider value={{ session, isLoading, resetSession, setSelectedClientId }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
