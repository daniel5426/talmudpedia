"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DirectionMode = "rtl" | "ltr";

type DirectionContextValue = {
  direction: DirectionMode;
  setDirection: (mode: DirectionMode) => void;
  toggleDirection: () => void;
};

const DirectionContext = createContext<DirectionContextValue | null>(null);

type DirectionProviderProps = {
  children: ReactNode;
  initialDirection: DirectionMode;
};

export function DirectionProvider({
  children,
  initialDirection,
}: DirectionProviderProps) {
  const [direction, setDirection] = useState<DirectionMode>(initialDirection);

  const toggleDirection = useCallback(() => {
    setDirection((prev) => (prev === "rtl" ? "ltr" : "rtl"));
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    root.setAttribute("dir", direction);
    body?.setAttribute("dir", direction);
    body?.setAttribute("data-direction", direction);
    document.cookie = `talmudpedia-direction=${direction}; path=/; max-age=31536000; SameSite=Lax`;
    try {
      window.localStorage.setItem("talmudpedia-direction", direction);
    } catch {}
  }, [direction]);

  const value = useMemo(
    () => ({
      direction,
      setDirection,
      toggleDirection,
    }),
    [direction, toggleDirection]
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

