"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

const AUTH_UNLOCK_STORAGE_KEY = "agents24-auth-unlocked";
const authAccessListeners = new Set<() => void>();

type AuthAccessContextValue = {
  authUnlocked: boolean;
  registerSecretTap: () => void;
};

const AuthAccessContext = createContext<AuthAccessContextValue | null>(null);

function emitAuthAccessChange() {
  authAccessListeners.forEach((listener) => listener());
}

function subscribeToAuthAccess(listener: () => void) {
  authAccessListeners.add(listener);

  const onStorage = (event: StorageEvent) => {
    if (event.key === AUTH_UNLOCK_STORAGE_KEY) {
      listener();
    }
  };

  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }

  return () => {
    authAccessListeners.delete(listener);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

function getAuthAccessSnapshot() {
  if (typeof window === "undefined") {
    return false;
  }

  return window.sessionStorage.getItem(AUTH_UNLOCK_STORAGE_KEY) === "1";
}

export function AuthAccessProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const authUnlocked = useSyncExternalStore(
    subscribeToAuthAccess,
    getAuthAccessSnapshot,
    () => false,
  );
  const [tapCount, setTapCount] = useState(0);
  const resetTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (tapCount === 0) {
      return;
    }

    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
    }

    resetTimerRef.current = window.setTimeout(() => {
      setTapCount(0);
    }, 1400);

    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, [tapCount]);

  const registerSecretTap = useCallback(() => {
    if (authUnlocked || typeof window === "undefined") {
      return;
    }

    setTapCount((current) => {
      const nextCount = current + 1;
      if (nextCount < 3) {
        return nextCount;
      }

      window.sessionStorage.setItem(AUTH_UNLOCK_STORAGE_KEY, "1");
      emitAuthAccessChange();
      return 0;
    });
  }, [authUnlocked]);

  const value = useMemo(
    () => ({
      authUnlocked,
      registerSecretTap,
    }),
    [authUnlocked, registerSecretTap],
  );

  return (
    <AuthAccessContext.Provider value={value}>
      {children}
    </AuthAccessContext.Provider>
  );
}

export function useAuthAccess() {
  const context = useContext(AuthAccessContext);

  if (!context) {
    throw new Error("useAuthAccess must be used inside AuthAccessProvider");
  }

  return context;
}
