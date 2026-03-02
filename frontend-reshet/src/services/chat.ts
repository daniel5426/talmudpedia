import type {
  ChatFetchParams,
  ChatHistory,
  ChatPagination,
} from "./types";

class ChatService {
  async list(params?: ChatFetchParams): Promise<ChatPagination> {
    return {
      items: [],
      nextCursor: null,
    };
  }

  async getHistory(chatId: string): Promise<ChatHistory> {
    throw new Error("Legacy chat history endpoint has been removed.");
  }

  async delete(chatId: string): Promise<void> {
    return;
  }

  async updateMessageFeedback(
    chatId: string,
    messageIndex: number,
    feedback: { liked?: boolean; disliked?: boolean }
  ): Promise<void> {
    return;
  }

  async deleteLastAssistantMessage(chatId: string): Promise<void> {
    return;
  }

  async sendMessage(
    message: string,
    chatId?: string,
    files?: any[],
    signal?: AbortSignal
  ): Promise<Response> {
    throw new Error("Legacy chat endpoint has been removed.");
  }

  getShareUrl(chatId: string): string {
    return `${window.location.origin}/admin/agents/playground`;
  }
}

export const chatService = new ChatService();
