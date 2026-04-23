import { httpClient } from "./http";
import type {
  AuthSessionBootstrapResponse,
  AuthSessionResponse,
  OnboardingOrganizationResponse,
  OrganizationSwitchResponse,
  User,
} from "./types";

const AUTH_SESSION_TIMEOUT_MS = 8000;
const AUTH_NAV_BASE_URL = String(process.env.NEXT_PUBLIC_BACKEND_URL || "").trim().replace(/\/$/, "");
const AUTH_REQUEST_INIT = { cache: "no-store" as const };

class AuthService {
  private currentSessionPromise: Promise<AuthSessionBootstrapResponse> | null = null;

  private buildReturnTo(target: string): string {
    if (/^https?:\/\//i.test(target)) {
      return target;
    }
    return target.startsWith("/") ? target : `/${target}`;
  }

  private getAuthNavBaseUrl(): string {
    if (AUTH_NAV_BASE_URL) {
      return AUTH_NAV_BASE_URL;
    }

    if (typeof window !== "undefined") {
      const { protocol, hostname } = window.location;
      if (hostname === "localhost" || hostname === "127.0.0.1") {
        return `${protocol}//${hostname}:8026`;
      }
    }

    return "";
  }

  getLoginUrl(returnTo = "/admin/agents/playground"): string {
    return `${this.getAuthNavBaseUrl()}/auth/login?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  getSignupUrl(returnTo = "/admin/agents/playground"): string {
    return `${this.getAuthNavBaseUrl()}/auth/signup?return_to=${encodeURIComponent(this.buildReturnTo(returnTo))}`;
  }

  async getCurrentSession(): Promise<AuthSessionBootstrapResponse> {
    if (this.currentSessionPromise) {
      return this.currentSessionPromise;
    }

    const request = httpClient.get<AuthSessionBootstrapResponse>("/auth/session", {
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

  async switchOrganization(organizationId: string, returnTo?: string): Promise<OrganizationSwitchResponse> {
    return httpClient.post<OrganizationSwitchResponse>("/auth/context/organization", {
      organization_id: organizationId,
      return_to: returnTo ? this.buildReturnTo(returnTo) : undefined,
    }, AUTH_REQUEST_INIT);
  }

  async switchProject(projectId: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/context/project", {
      project_id: projectId,
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

export function isAuthSessionRedirectResponse(
  response: AuthSessionBootstrapResponse,
): response is { redirect_url: string } {
  return "redirect_url" in response;
}

export function navigateToAuthRedirect(url: string): void {
  window.location.assign(url);
}
