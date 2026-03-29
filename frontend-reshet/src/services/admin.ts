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
    endDate?: string,
    options?: { agentId?: string }
  ): Promise<StatsSummaryResponse> {
    const params = new URLSearchParams({ section, days: String(days) });
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    if (options?.agentId) params.set("agent_id", options.agentId);
    return httpClient.get<StatsSummaryResponse>(
      `/admin/stats/summary?${params.toString()}`
    );
  }

  async getUsers(
    page = 1,
    limit = 20,
    search = "",
    options?: { actorType?: string; agentId?: string; appId?: string }
  ): Promise<UserListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    if (options?.actorType) query.set("actor_type", options.actorType);
    if (options?.agentId) query.set("agent_id", options.agentId);
    if (options?.appId) query.set("app_id", options.appId);
    return httpClient.get<UserListResponse>(`/admin/users?${query.toString()}`);
  }

  async getThreads(
    page = 1,
    limit = 20,
    search = "",
    options?: { actorType?: string; surface?: string; agentId?: string; appId?: string }
  ): Promise<ThreadListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    if (options?.actorType) query.set("actor_type", options.actorType);
    if (options?.surface) query.set("surface", options.surface);
    if (options?.agentId) query.set("agent_id", options.agentId);
    if (options?.appId) query.set("app_id", options.appId);
    return httpClient.get<ThreadListResponse>(`/admin/threads?${query.toString()}`);
  }

  async getUserDetails(userId: string): Promise<UserDetailsResponse> {
    return httpClient.get<UserDetailsResponse>(`/admin/users/${userId}`);
  }

  async getUserThreads(
    userId: string,
    page = 1,
    limit = 20,
    search = "",
    options?: { agentId?: string }
  ): Promise<ThreadListResponse> {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set("search", search);
    if (options?.agentId) query.set("agent_id", options.agentId);
    const queryString = query.toString();
    return httpClient.get<ThreadListResponse>(`/admin/users/${userId}/threads?${queryString}`);
  }

  async getThread(
    threadId: string,
    options?: { beforeTurnIndex?: number; limit?: number }
  ): Promise<Record<string, unknown>> {
    const query = new URLSearchParams();
    if (typeof options?.beforeTurnIndex === "number") query.set("before_turn_index", String(options.beforeTurnIndex));
    if (typeof options?.limit === "number") query.set("limit", String(options.limit));
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return httpClient.get<Record<string, unknown>>(`/admin/threads/${threadId}${suffix}`);
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
