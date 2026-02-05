import { httpClient } from "./http";

export interface TranscribeResponse {
  text: string;
}

class STTService {
  async transcribe(formData: FormData): Promise<TranscribeResponse> {
    // We use requestRaw because we are sending FormData which httpClient handles,
    // but the typed methods like .post() might accept object/json body more naturally.
    // However, httpClient.post checks for FormData.
    // Let's use httpClient.post<TranscribeResponse>
    
    // Note: The endpoint path in prompt-input was "/api/py/stt/transcribe"
    return httpClient.post<TranscribeResponse>("/stt/transcribe", formData);
  }
}

export const sttService = new STTService();
