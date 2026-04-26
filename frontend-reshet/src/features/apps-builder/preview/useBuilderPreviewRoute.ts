"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  extractAppsBuilderPreviewRoutes,
  normalizeAppsBuilderPreviewRoute,
} from "@/services/apps-builder-preview-routes";

type UseBuilderPreviewRouteOptions = {
  files: Record<string, string>;
  resetKey: string;
};

export type BuilderPreviewRouteState = {
  previewRoute: string;
  previewRouteInput: string;
  isPreviewRoutePickerOpen: boolean;
  appRoutes: string[];
  rankedAppRoutes: string[];
  preserveVisibleFrameOnRouteSync: boolean;
  setPreviewRouteInput: (value: string) => void;
  setIsPreviewRoutePickerOpen: (value: boolean) => void;
  navigatePreview: (route: string) => void;
  handlePreviewRouteChange: (route: string) => void;
};

function rankRoutes(routes: string[], queryValue: string): string[] {
  const query = queryValue.trim().toLowerCase();
  const scoreRoute = (route: string): number => {
    const normalized = route.toLowerCase();
    if (!query) return 0;
    if (normalized === query) return 0;
    if (normalized.startsWith(query)) return 1;
    if (normalized.includes(query)) return 2;
    return 3;
  };
  return [...routes].sort((left, right) => (
    scoreRoute(left) - scoreRoute(right)
    || left.localeCompare(right)
  ));
}

export function useBuilderPreviewRoute({
  files,
  resetKey,
}: UseBuilderPreviewRouteOptions): BuilderPreviewRouteState {
  const [previewRoute, setPreviewRoute] = useState("/");
  const [previewRouteInput, setPreviewRouteInput] = useState("/");
  const [isPreviewRoutePickerOpen, setIsPreviewRoutePickerOpen] = useState(false);
  const iframeSyncedPreviewRouteRef = useRef<string | null>(null);

  useEffect(() => {
    iframeSyncedPreviewRouteRef.current = null;
    setPreviewRoute("/");
    setPreviewRouteInput("/");
    setIsPreviewRoutePickerOpen(false);
  }, [resetKey]);

  const appRoutes = useMemo(() => extractAppsBuilderPreviewRoutes(files), [files]);
  const rankedAppRoutes = useMemo(
    () => rankRoutes(appRoutes, previewRouteInput),
    [appRoutes, previewRouteInput],
  );

  const navigatePreview = useCallback((route: string) => {
    const normalizedRoute = normalizeAppsBuilderPreviewRoute(route) || "/";
    iframeSyncedPreviewRouteRef.current = null;
    setPreviewRoute(normalizedRoute);
    setPreviewRouteInput(normalizedRoute);
    setIsPreviewRoutePickerOpen(false);
  }, []);

  const handlePreviewRouteChange = useCallback((route: string) => {
    const normalizedRoute = normalizeAppsBuilderPreviewRoute(route);
    if (!normalizedRoute) {
      return;
    }
    iframeSyncedPreviewRouteRef.current = normalizedRoute;
    setPreviewRoute((current) => (current === normalizedRoute ? current : normalizedRoute));
    setPreviewRouteInput((current) => (current === normalizedRoute ? current : normalizedRoute));
  }, []);

  useEffect(() => {
    setPreviewRouteInput(previewRoute);
    if (iframeSyncedPreviewRouteRef.current === previewRoute) {
      iframeSyncedPreviewRouteRef.current = null;
    }
  }, [previewRoute]);

  return {
    previewRoute,
    previewRouteInput,
    isPreviewRoutePickerOpen,
    appRoutes,
    rankedAppRoutes,
    preserveVisibleFrameOnRouteSync: iframeSyncedPreviewRouteRef.current === previewRoute,
    setPreviewRouteInput,
    setIsPreviewRoutePickerOpen,
    navigatePreview,
    handlePreviewRouteChange,
  };
}
