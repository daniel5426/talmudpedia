import { useAuthStore } from "@/lib/store/useAuthStore";

class LivekitService {
  async getToken(roomId: string, username: string, chatId?: string): Promise<{ token: string }> {
    const params = new URLSearchParams({
      room: roomId,
      username: username,
    });

    if (chatId) {
      params.append("chatId", chatId);
    }

    const token = useAuthStore.getState().token;
    const headers: HeadersInit = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`/api/livekit?${params.toString()}`, { headers });
    if (!response.ok) {
      throw new Error("Failed to fetch livekit token: " + await response.text());
    }
    return response.json();
  }
}

export const livekitService = new LivekitService();
