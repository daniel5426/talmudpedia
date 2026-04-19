import { httpClient } from "./http";
import type {
  AuthSessionResponse,
  OnboardingOrganizationResponse,
  OrganizationSwitchResponse,
  User,
} from "./types";

const AUTH_SESSION_TIMEOUT_MS = 8000;
const BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "/api/py";

class AuthService {
  private currentSessionPromise: Promise<AuthSessionResponse> | null = null;

  private buildReturnTo(target: string): string {
    if (/^https?:\/\//i.test(target)) {
      return target;
    }
    const origin =
      process.env.NEXT_PUBLIC_APP_URL ||
      (typeof window !== "undefined" ? window.location.origin : "");
    if (!origin) {
      return target;
    }
    return `${origin}${target.startsWith("/") ? target : `/${target}`}`;
  }

  getLoginUrl(returnTo = "/admin/agents/playground"): string {
    return `${BASE_URL}/auth/login?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  getSignupUrl(returnTo = "/admin/agents/playground"): string {
    return `${BASE_URL}/auth/signup?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  async getCurrentSession(): Promise<AuthSessionResponse> {
    if (this.currentSessionPromise) {
      return this.currentSessionPromise;
    }

    const request = httpClient.get<AuthSessionResponse>("/auth/session", {
      clearSessionOn401: true,
      timeoutMs: AUTH_SESSION_TIMEOUT_MS,
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
    return httpClient.get<User>("/auth/me");
  }

  async logout(): Promise<{ status: string; logout_url?: string | null }> {
    return httpClient.post<{ status: string; logout_url?: string | null }>("/auth/logout");
  }

  async switchOrganization(organizationSlug: string, returnTo?: string): Promise<OrganizationSwitchResponse> {
    return httpClient.post<OrganizationSwitchResponse>("/auth/context/organization", {
      organization_slug: organizationSlug,
      return_to: returnTo ? this.buildReturnTo(returnTo) : undefined,
    });
  }

  async switchProject(projectSlug: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/context/project", {
      project_slug: projectSlug,
    });
  }

  async createOnboardingOrganization(name: string, returnTo?: string): Promise<OnboardingOrganizationResponse> {
    return httpClient.post<OnboardingOrganizationResponse>("/auth/onboarding/organization", {
      name,
      return_to: returnTo ? this.buildReturnTo(returnTo) : undefined,
    });
  }
}

export const authService = new AuthService();
