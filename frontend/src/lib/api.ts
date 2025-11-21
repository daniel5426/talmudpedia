const API_BASE = '/api/py';

export interface Chat {
  id: string;
  title: string;
  updated_at: string;
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Array<{ title: string; url: string; description: string }>;
  reasoning_steps?: Array<{ step: string; status: string; message: string }>;
}

export interface ChatHistory {
  id: string;
  title: string;
  messages: Message[];
}

export interface ChatPagination {
  items: Chat[];
  nextCursor: string | null;
}

export interface ChatFetchParams {
  cursor?: string;
  limit?: number;
}

export const api = {
  getChats: async (params?: ChatFetchParams): Promise<ChatPagination> => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.cursor) query.set('cursor', params.cursor);
    const url = query.toString() ? `${API_BASE}/chats?${query.toString()}` : `${API_BASE}/chats`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch chats');
    return res.json();
  },

  getChatHistory: async (chatId: string): Promise<ChatHistory> => {
    const res = await fetch(`${API_BASE}/chats/${chatId}`);
    if (!res.ok) throw new Error('Failed to fetch chat history');
    return res.json();
  },

  deleteChat: async (chatId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/chats/${chatId}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete chat');
  },
};
