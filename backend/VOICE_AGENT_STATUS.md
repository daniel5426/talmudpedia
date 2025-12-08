Voice mode agent status (LiveKit + LangGraph)
=============================================

Overview
- LiveKit worker entrypoint: `backend/app/workers/livekit_worker.py`
- Uses LiveKit Agents with LangGraph workflow via `lk_langchain.LLMAdapter`.
- Assistant persists chat turns through `VoiceSessionManager` (user and assistant).

LLM / RAG
- Workflow: `AdvancedRAGWorkflow` (LangGraph) with `OpenAILLM('gpt-5-chat-latest')`.
- Vector retrieval via `VectorRetriever` (hybrid retriever inside workflow).
- Adapter: wrapped `LLMAdapter` with persistence stream to save assistant output.

STT
- Provider: OpenAI STT (`openai.STT`) with realtime enabled.
- Language: `LIVEKIT_STT_LANGUAGE` (default he), optional detect via `LIVEKIT_STT_DETECT_LANGUAGE=1`.
- Prompt: `LIVEKIT_STT_PROMPT` if set.

TTS
- Default provider: Cartesia (`LIVEKIT_TTS_PROVIDER=cartesia`).
- Model: `CARTESIA_TTS_MODEL` default `sonic-3`.
- Voice: `CARTESIA_TTS_VOICE` (env override).
- Language: `CARTESIA_TTS_LANGUAGE` default `he`.
- Speed: `CARTESIA_TTS_SPEED` default 1.0.
- Word timestamps auto-enabled for supported langs/models.
- Wrapped with `livekit.agents.tts.StreamAdapter` to ensure streaming and pacing.
- Fallback provider path: OpenAI TTS (`LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE`, optional `LIVEKIT_TTS_INSTRUCTIONS`).

Audio / VAD / room input
- VAD: `silero.VAD.load()`.
- Audio filtering: Currently disabled (APM module not available).
- Note: Echo cancellation, noise suppression previously attempted but caused errors.
- Auto-subscribe: audio-only on connect.

Event handling and persistence
- Participant metadata parsing for `userId` and `chatId` via room events queue.
- User and assistant speech commits are buffered and saved to MongoDB.
- AgentSession error hook patched for logging; log queue handler patched to avoid exc_info tuple issues.
- LangGraph `_to_chat_chunk` patched to use `.text` property to avoid deprecation noise; warning filtered by message.

Session lifecycle and shutdown
- Worker watches parent PID to terminate when main process exits.
- AgentSession graceful close and session finalization persist buffered messages and updates chat title.

Known env vars of interest
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `LIVEKIT_TTS_PROVIDER`, `CARTESIA_TTS_MODEL`, `CARTESIA_TTS_VOICE`, `CARTESIA_TTS_LANGUAGE`, `CARTESIA_TTS_SPEED`
- `LIVEKIT_STT_MODEL`, `LIVEKIT_STT_LANGUAGE`, `LIVEKIT_STT_DETECT_LANGUAGE`, `LIVEKIT_STT_PROMPT`
- `LIVEKIT_TTS_MODEL`, `LIVEKIT_TTS_VOICE`, `LIVEKIT_TTS_INSTRUCTIONS`

