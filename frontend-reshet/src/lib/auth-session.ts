import { useAuthStore } from "@/lib/store/useAuthStore";
import type { AuthSessionResponse } from "@/services/types";

export function applyAuthSession(session: AuthSessionResponse): void {
  useAuthStore.getState().setSession({
    user: session.user,
    activeOrganization: session.active_organization,
    activeProject: session.active_project,
    organizations: session.organizations,
    projects: session.projects,
    effectiveScopes: session.effective_scopes,
  });
}

export function clearAuthSession(): void {
  useAuthStore.getState().clearSession();
}
