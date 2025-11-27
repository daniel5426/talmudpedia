import { useAuthStore } from './store/useAuthStore';

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
  attachments?: Array<{ name: string; type: string; content: string }>;
}

export interface ChatHistory {
  id: string;
  title: string;
  messages: Message[];
  created_at: string;
}

export interface ChatPagination {
  items: Chat[];
  nextCursor: string | null;
}

export interface ChatFetchParams {
  cursor?: string;
  limit?: number;
}

export interface User {
  id: string;
  email: string;
  full_name?: string;
  avatar?: string;
  role?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AdminStats {
  total_users: number;
  total_active_users: number;
  total_chats: number;
  total_messages: number;
  avg_messages_per_chat: number;
  estimated_tokens: number;
  new_users_last_7_days: number;
  daily_active_users: Array<{ date: string; count: number }>;
  daily_stats: Array<{ date: string; chats: number }>;
  top_users: Array<{ email: string; count: number }>;
  latest_chats: Array<{ id: string; title: string; created_at: string; user_email?: string }>;
}

export interface UserListResponse {
  items: User[];
  total: number;
  page: number;
  pages: number;
}

export interface ChatListResponse {
  items: Chat[];
  total: number;
  page: number;
  pages: number;
}

export interface UserDetailsResponse {
  user: User;
  stats: {
    chats_count: number;
    tokens_used_this_month: number;
  };
}

const getHeaders = () => {
  const token = useAuthStore.getState().token;
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
};

export const api = {
  login: async (email: string, password: string): Promise<AuthResponse> => {
    const formData = new FormData();
    formData.append('username', email);
    formData.append('password', password);
    
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      body: formData,
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Login failed');
    }
    return res.json();
  },

  register: async (email: string, password: string, fullName?: string): Promise<User> => {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    
    if (!res.ok) {
      const error = await res.json();
      throw new Error(error.detail || 'Registration failed');
    }
    return res.json();
  },

  getMe: async (): Promise<User> => {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to fetch user profile');
    return res.json();
  },

  getChats: async (params?: ChatFetchParams): Promise<ChatPagination> => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.cursor) query.set('cursor', params.cursor);
    const url = query.toString() ? `${API_BASE}/chats?${query.toString()}` : `${API_BASE}/chats`;
    const res = await fetch(url, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch chats');
    return res.json();
  },

  getChatHistory: async (chatId: string): Promise<ChatHistory> => {
    const res = await fetch(`${API_BASE}/chats/${chatId}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch chat history');
    return res.json();
  },

  deleteChat: async (chatId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/chats/${chatId}`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to delete chat');
  },

  getAdminStats: async (startDate?: string, endDate?: string): Promise<AdminStats> => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const url = params.toString() ? `${API_BASE}/admin/stats?${params.toString()}` : `${API_BASE}/admin/stats`;
    const res = await fetch(url, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch admin stats');
    return res.json();
  },

  getAdminUsers: async (page = 1, limit = 20, search = ''): Promise<UserListResponse> => {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set('search', search);
    
    const res = await fetch(`${API_BASE}/admin/users?${query.toString()}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch users');
    return res.json();
  },

  getAdminChats: async (page = 1, limit = 20, search = ''): Promise<ChatListResponse> => {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set('search', search);
    
    const res = await fetch(`${API_BASE}/admin/chats?${query.toString()}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch chats');
    return res.json();
  },

  getAdminUserDetails: async (userId: string): Promise<UserDetailsResponse> => {
    const res = await fetch(`${API_BASE}/admin/users/${userId}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch user details');
    return res.json();
  },

  getAdminUserChats: async (userId: string, page = 1, limit = 20, search = ''): Promise<ChatListResponse> => {
    const skip = (page - 1) * limit;
    const query = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (search) query.set('search', search);
    
    const res = await fetch(`${API_BASE}/admin/users/${userId}/chats?${query.toString()}`, { headers: getHeaders() });
    if (!res.ok) throw new Error('Failed to fetch user chats');
    return res.json();
  },

  updateUser: async (userId: string, data: { full_name?: string; role?: string }): Promise<void> => {
    const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
      method: 'PATCH',
      headers: getHeaders(),
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update user');
  },

  bulkDeleteUsers: async (userIds: string[]): Promise<void> => {
    const res = await fetch(`${API_BASE}/admin/users/bulk-delete`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(userIds),
    });
    if (!res.ok) throw new Error('Failed to bulk delete users');
  },

  bulkDeleteChats: async (chatIds: string[]): Promise<void> => {
    const res = await fetch(`${API_BASE}/admin/chats/bulk-delete`, {
      method: 'POST',
      headers: getHeaders(),
      body: JSON.stringify(chatIds),
    });
    if (!res.ok) throw new Error('Failed to bulk delete chats');
  },

  updateMessageFeedback: async (
    chatId: string,
    messageIndex: number,
    feedback: { liked?: boolean; disliked?: boolean }
  ): Promise<void> => {
    const params = new URLSearchParams();
    if (feedback.liked !== undefined) params.set('liked', String(feedback.liked));
    if (feedback.disliked !== undefined) params.set('disliked', String(feedback.disliked));
    
    const res = await fetch(`${API_BASE}/chats/${chatId}/messages/${messageIndex}?${params.toString()}`, {
      method: 'PATCH',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to update message feedback');
  },

  deleteLastAssistantMessage: async (chatId: string): Promise<void> => {
    const res = await fetch(`${API_BASE}/chats/${chatId}/messages/last-assistant`, {
      method: 'DELETE',
      headers: getHeaders(),
    });
    if (!res.ok) throw new Error('Failed to delete last assistant message');
  },
};
