import { httpClient } from "./http";
import type {
  AdminStats,
  ChatListResponse,
  User,
  UserDetailsResponse,
  UserListResponse,
} from "./types";

class AdminService {
  async getStats(startDate?: string, endDate?: string): Promise<AdminStats> {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    const queryString = params.toString();
    const path = queryString ? `/admin/stats?${queryString}` : "/admin/stats";
    return httpClient.get<AdminStats>(path);
  }

  async getUsers(page = 1, limit = 20, search = ""): Promise<UserListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    return httpClient.get<UserListResponse>(`/admin/users?${query.toString()}`);
  }

  async getChats(page = 1, limit = 20, search = ""): Promise<ChatListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    return httpClient.get<ChatListResponse>(`/admin/chats?${query.toString()}`);
  }

  async getUserDetails(userId: string): Promise<UserDetailsResponse> {
    return httpClient.get<UserDetailsResponse>(`/admin/users/${userId}`);
  }

  async getUserChats(
    userId: string,
    page = 1,
    limit = 20,
    search = ""
  ): Promise<ChatListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    const queryString = query.toString();
    return httpClient.get<ChatListResponse>(`/admin/users/${userId}/chats?${queryString}`);
  }

  async updateUser(userId: string, data: { full_name?: string; role?: string }): Promise<void> {
    return httpClient.patch<void>(`/admin/users/${userId}`, data);
  }

  async bulkDeleteUsers(userIds: string[]): Promise<void> {
    return httpClient.post<void>("/admin/users/bulk-delete", userIds);
  }

  async bulkDeleteChats(chatIds: string[]): Promise<void> {
    return httpClient.post<void>("/admin/chats/bulk-delete", chatIds);
  }
}

export const adminService = new AdminService();
