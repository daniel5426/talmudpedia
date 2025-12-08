import { useAuthStore } from "@/lib/store/useAuthStore";

class TTSService {
  async speak(text: string): Promise<Blob> {
    const token = useAuthStore.getState().token;
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch("/api/py/tts/speak", {
      method: "POST",
      headers,
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || "Failed to synthesize speech");
    }

    return response.blob();
  }

  async stream(text: string, signal?: AbortSignal): Promise<{ url: string; cleanup: () => void }> {
    const token = useAuthStore.getState().token;
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch("/api/py/tts/speak", {
      method: "POST",
      headers,
      body: JSON.stringify({ text }),
      signal,
    });

    if (!response.ok || !response.body) {
      const errorText = await response.text();
      throw new Error(errorText || "Failed to stream speech");
    }

    const mediaSource = new MediaSource();
    const url = URL.createObjectURL(mediaSource);

    const reader = response.body.getReader();

    const cleanup = () => {
      try {
        if (mediaSource.readyState === "open") {
          mediaSource.endOfStream();
        }
      } catch {
        // ignore
      }
      URL.revokeObjectURL(url);
      reader.cancel().catch(() => {});
    };

    mediaSource.addEventListener("sourceopen", () => {
      const sourceBuffer = mediaSource.addSourceBuffer("audio/mpeg");
      let done = false;
      const queue: Uint8Array[] = [];

      const append = () => {
        if (!queue.length || sourceBuffer.updating) return;
        const chunk = queue.shift();
        if (chunk) {
          sourceBuffer.appendBuffer(chunk);
        }
      };

      sourceBuffer.addEventListener("updateend", () => {
        if (done && queue.length === 0) {
          try {
            mediaSource.endOfStream();
          } catch {
            // ignore
          }
        } else {
          append();
        }
      });

      const pump = async () => {
        try {
          while (true) {
            const { done: readerDone, value } = await reader.read();
            if (readerDone) {
              done = true;
              if (!sourceBuffer.updating) {
                try {
                  mediaSource.endOfStream();
                } catch {
                  // ignore
                }
              }
              break;
            }
            if (value) {
              queue.push(value);
              if (!sourceBuffer.updating) {
                append();
              }
            }
          }
        } catch {
          cleanup();
        }
      };

      pump();
    });

    return { url, cleanup };
  }
}

export const ttsService = new TTSService();
