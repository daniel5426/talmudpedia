"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";

export type DirectionMode = "rtl" | "ltr";

type DirectionContextValue = {
  direction: DirectionMode;
  setDirection: (mode: DirectionMode) => void;
  toggleDirection: () => void;
};

const DirectionContext = createContext<DirectionContextValue | null>(null);

const LOCKED_DIRECTION: DirectionMode = "ltr";

export function DirectionProvider({ children }: { children: ReactNode }) {
  const setDirection = useCallback(() => {}, []);
  const toggleDirection = useCallback(() => {}, []);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    root.setAttribute("dir", LOCKED_DIRECTION);
    body?.setAttribute("dir", LOCKED_DIRECTION);
    body?.setAttribute("data-direction", LOCKED_DIRECTION);
    document.cookie = `talmudpedia-direction=${LOCKED_DIRECTION}; path=/; max-age=31536000; SameSite=Lax`;
    try {
      window.localStorage.setItem("talmudpedia-direction", LOCKED_DIRECTION);
    } catch {}
  }, []);

  const value = useMemo(
    () => ({
      direction: LOCKED_DIRECTION,
      setDirection,
      toggleDirection,
    }),
    [setDirection, toggleDirection],
  );

  return (
    <DirectionContext.Provider value={value}>
      {children}
    </DirectionContext.Provider>
  );
}

export function useDirection() {
  const context = useContext(DirectionContext);
  if (!context) {
    throw new Error("useDirection must be used within DirectionProvider");
  }
  return context;
}
