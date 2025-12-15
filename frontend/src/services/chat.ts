import { httpClient } from "./http";
import type {
  ChatFetchParams,
  ChatHistory,
  ChatPagination,
} from "./types";

class ChatService {
  async list(params?: ChatFetchParams): Promise<ChatPagination> {
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);
    const queryString = query.toString();
    const path = queryString ? `/chats?${queryString}` : "/chats";
    return httpClient.get<ChatPagination>(path);
  }

  async getHistory(chatId: string): Promise<ChatHistory> {
    return httpClient.get<ChatHistory>(`/chats/${chatId}`);
  }

  async delete(chatId: string): Promise<void> {
    return httpClient.delete<void>(`/chats/${chatId}`);
  }

  async updateMessageFeedback(
    chatId: string,
    messageIndex: number,
    feedback: { liked?: boolean; disliked?: boolean }
  ): Promise<void> {
    const params = new URLSearchParams();
    if (feedback.liked !== undefined) params.set("liked", String(feedback.liked));
    if (feedback.disliked !== undefined) params.set("disliked", String(feedback.disliked));
    const queryString = params.toString();
    return httpClient.patch<void>(
      `/chats/${chatId}/messages/${messageIndex}${queryString ? `?${queryString}` : ""}`
    );
  }

  async deleteLastAssistantMessage(chatId: string): Promise<void> {
    return httpClient.delete<void>(`/chats/${chatId}/messages/last-assistant`);
  }

  async sendMessage(
    message: string,
    chatId?: string,
    files?: any[],
    signal?: AbortSignal
  ): Promise<Response> {
    const body: any = { message };
    if (chatId) body.chatId = chatId;
    if (files && files.length > 0) body.files = files;

    return httpClient.requestRaw("/api/py/chat", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    });
  }

  getShareUrl(chatId: string): string {
    const params = new URLSearchParams({ chatId });
    return `${window.location.origin}/chat?${params.toString()}`;
  }
}

export const chatService = new ChatService();
