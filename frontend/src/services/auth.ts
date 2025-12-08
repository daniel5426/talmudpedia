import { httpClient } from "./http";
import type { AuthResponse, User } from "./types";

class AuthService {
  async login(email: string, password: string): Promise<AuthResponse> {
    const formData = new FormData();
    formData.append("username", email);
    formData.append("password", password);
    return httpClient.post<AuthResponse>("/auth/login", formData);
  }

  async register(email: string, password: string, fullName?: string): Promise<User> {
    return httpClient.post<User>("/auth/register", {
      email,
      password,
      full_name: fullName,
    });
  }

  async getProfile(): Promise<User> {
    return httpClient.get<User>("/auth/me");
  }
}

export const authService = new AuthService();
