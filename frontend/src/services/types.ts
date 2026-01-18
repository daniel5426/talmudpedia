export interface Citation {
  title: string;
  url: string;
  description: string;
  sourceRef?: string;
  ref?: string;
}

export interface MessageAttachmentPayload {
  name: string;
  type: string;
  content: string;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  reasoning_steps?: Array<{ step: string; status: string; message: string }>;
  tool_calls?: { 
    reasoning?: Array<{ step: string; status: string; message: string; citations?: Citation[]; query?: string; sources?: any[] }>;
    citations?: Citation[];
  };
  attachments?: MessageAttachmentPayload[];
}

export interface Chat {
  id: string;
  title: string;
  updated_at: string;
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
  org_role?: string;
  tenant_id?: string;
  org_unit_id?: string;
  created_at?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface AdminStats {
  total_users: number;
  total_active_users: number;
  token_usage: Array<{ date: string; tokens: number }>;
  total_chats: number;
  total_chunks: number;
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
