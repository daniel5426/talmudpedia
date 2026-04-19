import { httpClient } from "./http";
import type {
  AuthSessionResponse,
  OnboardingOrganizationResponse,
  OrganizationSwitchResponse,
  User,
} from "./types";

const AUTH_SESSION_TIMEOUT_MS = 8000;
const AUTH_NAV_BASE_URL = "/api/py";
const AUTH_REQUEST_INIT = { cache: "no-store" as const };

class AuthService {
  private currentSessionPromise: Promise<AuthSessionResponse> | null = null;

  private buildReturnTo(target: string): string {
    if (/^https?:\/\//i.test(target)) {
      return target;
    }
    return target.startsWith("/") ? target : `/${target}`;
  }

  getLoginUrl(returnTo = "/admin/agents/playground"): string {
    return `${AUTH_NAV_BASE_URL}/auth/login?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  getSignupUrl(returnTo = "/admin/agents/playground"): string {
    return `${AUTH_NAV_BASE_URL}/auth/signup?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  async getCurrentSession(): Promise<AuthSessionResponse> {
    if (this.currentSessionPromise) {
      return this.currentSessionPromise;
    }

    const request = httpClient.get<AuthSessionResponse>("/auth/session", {
      clearSessionOn401: true,
      timeoutMs: AUTH_SESSION_TIMEOUT_MS,
      ...AUTH_REQUEST_INIT,
    });
    this.currentSessionPromise = request;

    try {
      return await request;
    } finally {
      if (this.currentSessionPromise === request) {
        this.currentSessionPromise = null;
      }
    }
  }

  async getProfile(): Promise<User> {
    return httpClient.get<User>("/auth/me", AUTH_REQUEST_INIT);
  }

  async logout(): Promise<{ status: string; logout_url?: string | null }> {
    return httpClient.post<{ status: string; logout_url?: string | null }>("/auth/logout", undefined, AUTH_REQUEST_INIT);
  }

  async switchOrganization(organizationSlug: string, returnTo?: string): Promise<OrganizationSwitchResponse> {
    return httpClient.post<OrganizationSwitchResponse>("/auth/context/organization", {
      organization_slug: organizationSlug,
      return_to: returnTo ? this.buildReturnTo(returnTo) : undefined,
    }, AUTH_REQUEST_INIT);
  }

  async switchProject(projectSlug: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/context/project", {
      project_slug: projectSlug,
    }, AUTH_REQUEST_INIT);
  }

  async createOnboardingOrganization(name: string, returnTo?: string): Promise<OnboardingOrganizationResponse> {
    return httpClient.post<OnboardingOrganizationResponse>("/auth/onboarding/organization", {
      name,
      return_to: returnTo ? this.buildReturnTo(returnTo) : undefined,
    }, AUTH_REQUEST_INIT);
  }
}

export const authService = new AuthService();
