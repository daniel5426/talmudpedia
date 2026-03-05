import { httpClient } from "./http";
import type {
  AdminStats,
  ThreadListResponse,
  UserDetailsResponse,
  UserListResponse,
  StatsSection,
  StatsSummaryResponse,
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

  async getStatsSummary(
    section: StatsSection,
    days: number = 7,
    startDate?: string,
    endDate?: string
  ): Promise<StatsSummaryResponse> {
    const params = new URLSearchParams({ section, days: String(days) });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    return httpClient.get<StatsSummaryResponse>(
      `/admin/stats/summary?${params.toString()}`
    );
  }

  async getUsers(page = 1, limit = 20, search = ""): Promise<UserListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    return httpClient.get<UserListResponse>(`/admin/users?${query.toString()}`);
  }

  async getThreads(page = 1, limit = 20, search = ""): Promise<ThreadListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    return httpClient.get<ThreadListResponse>(`/admin/threads?${query.toString()}`);
  }

  async getUserDetails(userId: string): Promise<UserDetailsResponse> {
    return httpClient.get<UserDetailsResponse>(`/admin/users/${userId}`);
  }

  async getUserThreads(
    userId: string,
    page = 1,
    limit = 20,
    search = ""
  ): Promise<ThreadListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    const queryString = query.toString();
    return httpClient.get<ThreadListResponse>(`/admin/users/${userId}/threads?${queryString}`);
  }

  async getThread(threadId: string): Promise<Record<string, unknown>> {
    return httpClient.get<Record<string, unknown>>(`/admin/threads/${threadId}`);
  }

  async updateUser(userId: string, data: { full_name?: string }): Promise<void> {
    return httpClient.patch<void>(`/admin/users/${userId}`, data);
  }

  async bulkDeleteUsers(userIds: string[]): Promise<void> {
    return httpClient.post<void>("/admin/users/bulk-delete", userIds);
  }

  async bulkDeleteThreads(threadIds: string[]): Promise<void> {
    return httpClient.post<void>("/admin/threads/bulk-delete", threadIds);
  }
}

export const adminService = new AdminService();
