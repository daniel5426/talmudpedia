import { httpClient } from "./http";
import type { AuthSessionResponse, User } from "./types";

const AUTH_SESSION_TIMEOUT_MS = 8000;

class AuthService {
  private currentSessionPromise: Promise<AuthSessionResponse> | null = null;

  async login(email: string, password: string): Promise<AuthSessionResponse> {
    const formData = new FormData();
    formData.append("username", email);
    formData.append("password", password);
    return httpClient.post<AuthSessionResponse>("/auth/login", formData);
  }

  async signup(email: string, password: string, fullName?: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/signup", {
      email,
      password,
      full_name: fullName,
    });
  }

  async register(email: string, password: string, fullName?: string): Promise<AuthSessionResponse> {
    return this.signup(email, password, fullName);
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

  async googleLogin(credential: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/google", { credential });
  }

  async logout(): Promise<{ status: string }> {
    return httpClient.post<{ status: string }>("/auth/logout");
  }

  async switchOrganization(organizationSlug: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/context/organization", {
      organization_slug: organizationSlug,
    });
  }

  async switchProject(projectSlug: string): Promise<AuthSessionResponse> {
    return httpClient.post<AuthSessionResponse>("/auth/context/project", {
      project_slug: projectSlug,
    });
  }
}

export const authService = new AuthService();
