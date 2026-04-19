import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { OrganizationSummary, ProjectSummary, User } from "@/services/types";

interface AuthState {
  authenticated: boolean;
  onboardingRequired: boolean;
  user: User | null;
  activeOrganization: OrganizationSummary | null;
  activeProject: ProjectSummary | null;
  organizations: OrganizationSummary[];
  projects: ProjectSummary[];
  effectiveScopes: string[];
  hydrated: boolean;
  sessionChecked: boolean;
  setSession: (input: {
    authenticated?: boolean;
    onboardingRequired?: boolean;
    user: User;
    activeOrganization: OrganizationSummary | null;
    activeProject: ProjectSummary | null;
    organizations: OrganizationSummary[];
    projects: ProjectSummary[];
    effectiveScopes: string[];
  }) => void;
  clearSession: () => void;
  markHydrated: () => void;
  markSessionChecked: () => void;
  isAuthenticated: () => boolean;
  hasScope: (scope: string) => boolean;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      authenticated: false,
      onboardingRequired: false,
      activeOrganization: null,
      activeProject: null,
      organizations: [],
      projects: [],
      effectiveScopes: [],
      hydrated: false,
      sessionChecked: false,
      setSession: ({ user, activeOrganization, activeProject, organizations, projects, effectiveScopes, authenticated = true, onboardingRequired = false }: any) =>
        set({
          authenticated,
          onboardingRequired,
          user,
          activeOrganization,
          activeProject,
          organizations,
          projects,
          effectiveScopes,
          sessionChecked: true,
        }),
      clearSession: () =>
        set({
          authenticated: false,
          onboardingRequired: false,
          user: null,
          activeOrganization: null,
          activeProject: null,
          organizations: [],
          projects: [],
          effectiveScopes: [],
          sessionChecked: true,
        }),
      markHydrated: () => set({ hydrated: true }),
      markSessionChecked: () => set({ sessionChecked: true }),
      isAuthenticated: () => get().authenticated && !!get().user,
      hasScope: (scope: string) => {
        const scopes = new Set(get().effectiveScopes || []);
        return scopes.has("*") || scopes.has(scope);
      },
    }),
    {
      name: "reshet-auth-storage",
      partialize: (state) => ({
        user: state.user,
        authenticated: state.authenticated,
        onboardingRequired: state.onboardingRequired,
        activeOrganization: state.activeOrganization,
        activeProject: state.activeProject,
        organizations: state.organizations,
        projects: state.projects,
        effectiveScopes: state.effectiveScopes,
      }),
      onRehydrateStorage: () => (state) => {
        state?.markHydrated();
      },
    }
  )
);
