import os
import asyncio
import json
import copy
import signal
import traceback
from dotenv import load_dotenv
from langchain_core.messages import BaseMessageChunk
import warnings

from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, WorkerOptions, llm, RoomInputOptions
from livekit.agents.utils.http_context import _close_http_ctx
from livekit.agents.ipc import log_queue
from livekit.agents.voice.agent_session import SessionConnectOptions as LKSessionConnectOptions
from livekit.agents.voice.agent_session import AgentSession as LKAgentSession
from livekit.plugins import openai, silero, cartesia, langchain as lk_langchain
import aiohttp
from livekit.agents import utils as lk_utils
from livekit import rtc as lk_rtc
from livekit.agents import tts as lk_tts

from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.retrieval.vector import VectorRetriever
from app.services.voice import VoiceSessionManager
from app.db.connection import MongoDatabase

load_dotenv()
warnings.filterwarnings(
    "ignore",
    message="Calling \\.text\\(\\) as a method is deprecated",
)

def _patch_log_queue_handler():
    original_emit = log_queue.LogQueueHandler.emit

    def emit(self, record):
        if record.exc_info and not isinstance(record.exc_info, tuple):
            record = copy.copy(record)
            record.exc_info = None
            record.exc_text = None
        return original_emit(self, record)

    log_queue.LogQueueHandler.emit = emit

_patch_log_queue_handler()

def _patch_agent_session_on_error():
    original_on_error = LKAgentSession._on_error

    def _on_error(self, error):
        try:
            print(
                "AgentSession error",
                getattr(error, "type", None),
                getattr(error, "recoverable", None),
                getattr(error, "error", error),
            )
        except Exception:
            pass
        return original_on_error(self, error)

    LKAgentSession._on_error = _on_error

_patch_agent_session_on_error()

def _patch_langgraph_to_chat_chunk():
    from livekit.plugins import langchain as lk_langchain_mod
    def _patched_to_chat_chunk(msg):
        message_id = lk_utils.shortuuid("LC_")
        content = None
        if isinstance(msg, str):
            content = msg
        elif isinstance(msg, BaseMessageChunk):
            text_attr = getattr(msg, "text", None)
            if callable(text_attr):
                content = text_attr()
            elif text_attr is not None:
                content = text_attr
            else:
                content = getattr(msg, "content", None)
            if getattr(msg, "id", None):
                message_id = msg.id
        if not content:
            return None
        return llm.ChatChunk(
            id=message_id,
            delta=llm.ChoiceDelta(role="assistant", content=content),
        )
    lk_langchain_mod.langgraph._to_chat_chunk = _patched_to_chat_chunk  # type: ignore

_patch_langgraph_to_chat_chunk()

def _patch_room_on_event():
    original = lk_rtc.room.Room._on_room_event
    def _safe(self, event):
        try:
            return original(self, event)
        except KeyError as e:
            try:
                print("Room _on_room_event KeyError", e, getattr(event, "room_event", None))
            except Exception:
                pass
    lk_rtc.room.Room._on_room_event = _safe

_patch_room_on_event()

async def _watch_parent(parent_pid: int, cancel_task: asyncio.Task):
    while True:
        await asyncio.sleep(2)
        if os.getppid() != parent_pid:
            cancel_task.cancel()
            break

# Patch aiohttp ClientSession to fix LiveKit proxy error
# Use proper class inheritance to preserve introspection
_OriginalClientSession = aiohttp.ClientSession

class PatchedClientSession(_OriginalClientSession):
    def __init__(self, *args, **kwargs):
        # Remove the proxy argument that newer aiohttp doesn't support
        kwargs.pop("proxy", None)
        super().__init__(*args, **kwargs)

aiohttp.ClientSession = PatchedClientSession

async def entrypoint(ctx: JobContext):
    try:
        print("[INIT] Starting entrypoint...")
        
        # Identity and context from participant metadata
        user_id = None
        chat_id = None
        tenant_id = None
        
        async def wait_for_participant():
            nonlocal user_id, chat_id, tenant_id
            print("[INIT] Checking for existing participants...")
            for participant in ctx.room.remote_participants.values():
                if participant.metadata:
                    try:
                        metadata = json.loads(participant.metadata)
                        user_id = metadata.get("userId")
                        chat_id = metadata.get("chatId")
                        tenant_id = metadata.get("tenantId")
                        print(f"[INIT] Found existing participant: user_id={user_id}, chat_id={chat_id}, tenant_id={tenant_id}")
                        return
                    except json.JSONDecodeError:
                        pass
            print("[INIT] No existing participants, waiting for participant to join...")
            joined = ctx.room.on("participant_connected")
            async with joined as queue:
                event = await queue.get()
                participant = event.participant
                print(f"[INIT] Participant connected: {participant.identity}")
                if participant.metadata:
                    try:
                        metadata = json.loads(participant.metadata)
                        user_id = metadata.get("userId")
                        chat_id = metadata.get("chatId")
                        tenant_id = metadata.get("tenantId")
                        print(f"[INIT] Participant metadata: user_id={user_id}, chat_id={chat_id}, tenant_id={tenant_id}")
                    except json.JSONDecodeError:
                        print("[INIT] Failed to parse participant metadata")
                        pass
                        
        print("[INIT] Waiting for participant...")
        try:
            await wait_for_participant()
        except Exception as e:
            print(f"[INIT ERROR] Failed waiting for participant: {e}")
            traceback.print_exc()
            raise
            
        # Validate and convert IDs to UUIDs
        from uuid import UUID
        def _to_uuid(val):
            if not val: return None
            try: return UUID(str(val))
            except: return None

        user_uuid = _to_uuid(user_id)
        chat_uuid = _to_uuid(chat_id)
        tenant_uuid = _to_uuid(tenant_id)

        if not tenant_uuid:
            # Fallback to a default tenant ID if needed, or error out
            print("[INIT] Warning: No tenant_id found, using environment default if available")
            tenant_uuid = _to_uuid(os.getenv("DEFAULT_TENANT_ID"))
            
        if not user_uuid:
            print("[INIT] Warning: No user_uuid found, using environment default if available")
            user_uuid = _to_uuid(os.getenv("DEFAULT_USER_ID"))

        if not tenant_uuid or not user_uuid:
            print("[INIT ERROR] Missing required tenant_id or user_id for persistence. Cannot proceed.")
            # raise Exception("Missing required identity metadata")
            # For now, allow proceed without persistence or with a mock? 
            # Better to show we need these for Phase 3 parity.
            pass

        print(f"[INIT] Connecting to LiveKit room...")
        try:
            await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
            print(f"[INIT] Connected to room: {ctx.room.name}")
        except Exception as e:
            print(f"[INIT ERROR] LiveKit connection failed: {e}")
            traceback.print_exc()
            raise
            
        # Database session management
        from app.db.postgres.engine import sessionmaker as async_sessionmaker
        db_session_factory = async_sessionmaker()
        db = await db_session_factory.__aenter__()

        print(f"[INIT] Creating session manager...")
        try:
            session_manager = VoiceSessionManager(
                db=db, 
                user_id=user_uuid, 
                tenant_id=tenant_uuid, 
                chat_id=chat_uuid
            )
            chat_uuid = await session_manager.ensure_chat()
            print(f"[INIT] Chat ensured: {chat_uuid}")
        except Exception as e:
            print(f"[INIT ERROR] Session manager creation failed: {e}")
            traceback.print_exc()
            raise
            
        print("[INIT] Loading chat history...")
        try:
            chat_history = await session_manager.load_chat_history()
            print(f"[INIT] Loaded {len(chat_history)} messages from history")
        except Exception as e:
            print(f"[INIT ERROR] Failed to load chat history: {e}")
            traceback.print_exc()
            raise
            
        print("[INIT] Initializing retriever...")
        try:
            retriever = VectorRetriever()
            print("[INIT] Retriever initialized")
        except Exception as e:
            print(f"[INIT ERROR] Retriever initialization failed: {e}")
            traceback.print_exc()
            raise
            
        print("[INIT] Initializing LLM component...")
        try:
            llm_component = OpenAILLM('gpt-5-chat-latest')
            print("[INIT] LLM component initialized")
        except Exception as e:
            print(f"[INIT ERROR] LLM initialization failed: {e}")
            traceback.print_exc()
            raise
            
        print("[INIT] Building RAG workflow...")
        try:
            from app.agent.workflows.advanced_rag import AdvancedRAGWorkflow
            rag_agent = AdvancedRAGWorkflow(llm=llm_component, retriever=retriever)
            rag_agent.compile()
            print("[INIT] RAG workflow compiled successfully")
        except Exception as e:
            print(f"[INIT ERROR] RAG workflow build failed: {e}")
            traceback.print_exc()
            raise
            
        print("[INIT] Wrapping LLM adapter...")
        llm_adapter = lk_langchain.LLMAdapter(graph=rag_agent.graph)
        
        # Get STT prompt to filter it out from user messages
        stt_prompt_text = os.getenv("LIVEKIT_STT_PROMPT")
        if stt_prompt_text:
            print(f"[INIT] STT prompt configured for filtering: '{stt_prompt_text}'")
        else:
            print("[INIT] No STT prompt configured")
        
        # Buffer for user messages - concatenate until AI responds
        # This MUST be defined before PersistingStream so it can be captured in closure
        user_message_buffer = []
        
        class PersistingLLM(llm.LLM):
            def __init__(self, base, session_manager):
                super().__init__()
                self.base = base
                self.session_manager = session_manager
            def chat(self, *, chat_ctx, tools=None, tool_choice=None, conn_options=None, **kwargs):
                for key in ("fnc_ctx", "temperature", "n", "parallel_tool_calls"):
                    kwargs.pop(key, None)
                base_stream = self.base.chat(
                    chat_ctx=chat_ctx,
                    tools=tools,
                    tool_choice=tool_choice,
                    conn_options=conn_options,
                    **kwargs,
                )
                return PersistingStream(base_stream, self.session_manager)
        class PersistingStream:
            def __init__(self, inner, session_manager):
                self.inner = inner
                self.session_manager = session_manager
            def __aiter__(self):
                return self._iter()
            async def __aenter__(self):
                enter = getattr(self.inner, "__aenter__", None)
                if enter:
                    await enter()
                return self
            async def __aexit__(self, exc_type, exc, tb):
                exit_fn = getattr(self.inner, "__aexit__", None)
                if exit_fn:
                    return await exit_fn(exc_type, exc, tb)
            async def _iter(self):
                buffer = ""
                async for chunk in self.inner:
                    delta = getattr(chunk, "delta", None)
                    content = getattr(delta, "content", None) if delta else None
                    if content:
                        buffer += content
                    yield chunk
                if buffer:
                    # First, save all buffered user messages as one concatenated message
                    if user_message_buffer:
                        concatenated_user_message = " ".join(user_message_buffer)
                        print(f"[PERSIST STREAM] Saving concatenated user message ({len(user_message_buffer)} parts): {concatenated_user_message[:100]}...")
                        self.session_manager.buffer_message("user", concatenated_user_message)
                        user_message_buffer.clear()
                        print("[PERSIST STREAM] User buffer cleared")
                    
                    # Now save the assistant message
                    print(f"[PERSIST STREAM] Saving assistant message: {buffer[:50]}...")
                    self.session_manager.buffer_message("assistant", buffer)
                    await self.session_manager.save_buffered_messages()
                    print(f"[PERSIST STREAM] Messages saved successfully")
        llm_adapter = PersistingLLM(llm_adapter, session_manager)
        print("[INIT] LLM adapter wrapped with persistence")
        
        print("[INIT] Setting up chat context...")
        instructions = (
            "You are a helpful and knowledgeable Jewish text assistant. "
            "You provide answers based on Talmudic and Halakhic sources. "
            "Keep your spoken responses concise and conversational."
        )
        chat_ctx = llm.ChatContext()
        chat_ctx.add_message(role="system", content=instructions)
        for msg in chat_history:
            if msg.type == "system":
                chat_ctx.add_message(role="system", content=msg.content)
            elif msg.type == "human":
                chat_ctx.add_message(role="user", content=msg.content)
            elif msg.type == "ai":
                chat_ctx.add_message(role="assistant", content=msg.content)
        print(f"[INIT] Chat context ready with {len(chat_history)} historical messages")
        
        print("[INIT] Creating agent...")
        agent = Agent(
            instructions=instructions,
            chat_ctx=chat_ctx,
        )
        print("[INIT] Agent created")
        
        print("[INIT] Configuring TTS...")
        tts_provider = os.getenv("LIVEKIT_TTS_PROVIDER", "cartesia")
        if tts_provider == "cartesia":
            cartesia_model = os.getenv("CARTESIA_TTS_MODEL") or "sonic-3"
            cartesia_voice = os.getenv("CARTESIA_TTS_VOICE")
            cartesia_language = os.getenv("CARTESIA_TTS_LANGUAGE") or "he"
            cartesia_word_timestamps = os.getenv("CARTESIA_TTS_WORD_TIMESTAMPS")
            cartesia_speed = float(os.getenv("CARTESIA_TTS_SPEED") or 1.0)
            cartesia_word_timestamps_enabled = (
                cartesia_word_timestamps == "1"
                if cartesia_word_timestamps is not None
                else "preview" in cartesia_model or cartesia_language in {"en", "de", "es", "fr"}
            )
            cartesia_kwargs = {
                "model": cartesia_model,
                "language": cartesia_language,
                "word_timestamps": cartesia_word_timestamps_enabled,
                "speed": cartesia_speed,
            }
            if cartesia_voice:
                cartesia_kwargs["voice"] = cartesia_voice
            
            # Add encoding for better quality
            cartesia_kwargs["encoding"] = "pcm_s16le"
            
            tts_instance = cartesia.TTS(**cartesia_kwargs)
            # Disable text_pacing to prevent stuttering and word repetition
            tts_instance = lk_tts.StreamAdapter(tts=tts_instance, text_pacing=False)
            print(f"[INIT] Cartesia TTS configured: model={cartesia_model}, language={cartesia_language}, text_pacing=False")
        else:
            tts_model = os.getenv("LIVEKIT_TTS_MODEL") or "gpt-4o-mini-tts"
            tts_voice = os.getenv("LIVEKIT_TTS_VOICE") or "ash"
            tts_instructions = os.getenv("LIVEKIT_TTS_INSTRUCTIONS") or "דבר בעברית ברורה. אם יש מילים באנגלית הוגה אותן באנגלית אבל השאר בעברית."
            tts_kwargs = {"model": tts_model, "voice": tts_voice}
            if tts_instructions:
                tts_kwargs["instructions"] = tts_instructions
            tts_instance = openai.TTS(**tts_kwargs)
            # Wrap with StreamAdapter for LiveKit streaming support
            tts_instance = lk_tts.StreamAdapter(tts=tts_instance, text_pacing=True)
            print(f"[INIT] OpenAI TTS configured: model={tts_model}, voice={tts_voice}")
        print("using tts model:", tts_instance.model)
        
        print("[INIT] Configuring STT...")
        stt_model = os.getenv("LIVEKIT_STT_MODEL")
        stt_language = os.getenv("LIVEKIT_STT_LANGUAGE") or "he"
        stt_detect = os.getenv("LIVEKIT_STT_DETECT_LANGUAGE") == "1"
        stt_prompt = os.getenv("LIVEKIT_STT_PROMPT")
        stt_kwargs = {
            "language": stt_language if not stt_detect else "en",
            "detect_language": stt_detect,
            "use_realtime": True,
        }
        if stt_model:
            stt_kwargs["model"] = stt_model
        if stt_prompt:
            stt_kwargs["prompt"] = stt_prompt
        print(f"[INIT] STT configured: language={stt_language}, detect={stt_detect}")
        
        print("[INIT] Creating AgentSession...")
        try:
            agent_session = AgentSession(
                vad=silero.VAD.load(),
                stt=openai.STT(**stt_kwargs),
                llm=llm_adapter,
                tts=tts_instance,
                conn_options=LKSessionConnectOptions(max_unrecoverable_errors=10),
            )
            print("[INIT] AgentSession created successfully")
        except Exception as e:
            print(f"[INIT ERROR] AgentSession creation failed: {e}")
            traceback.print_exc()
            raise
            
        async def persist_user_message(text):
            try:
                if not text:
                    print("[PERSIST] Skipping empty user message")
                    return
                
                # Normalize text for comparison
                normalized_text = text.strip().lower()
                
                # Filter out STT prompt with multiple checks
                if stt_prompt_text:
                    normalized_prompt = stt_prompt_text.strip().lower()
                    
                    # Exact match
                    if normalized_text == normalized_prompt:
                        print(f"[PERSIST] Filtering out STT prompt (exact match): {text[:50]}...")
                        return
                    
                    # Remove punctuation for comparison
                    text_no_punct = normalized_text.replace(".", "").replace("!", "").replace("?", "").replace(",", "").strip()
                    prompt_no_punct = normalized_prompt.replace(".", "").replace("!", "").replace("?", "").replace(",", "").strip()
                    
                    if text_no_punct == prompt_no_punct:
                        print(f"[PERSIST] Filtering out STT prompt (punctuation variation): {text[:50]}...")
                        return
                    
                    # Check if the text is just the prompt with extra whitespace or similar
                    if len(text_no_punct) > 0 and len(prompt_no_punct) > 0:
                        if text_no_punct in prompt_no_punct or prompt_no_punct in text_no_punct:
                            # Only filter if very similar in length (within 20%)
                            length_ratio = len(text_no_punct) / len(prompt_no_punct)
                            if 0.8 <= length_ratio <= 1.2:
                                print(f"[PERSIST] Filtering out STT prompt (similar text): {text[:50]}...")
                                return
                    
                # Just buffer the message, don't save yet
                print(f"[PERSIST] Buffering user message (not saved yet): {text[:50]}...")
                user_message_buffer.append(text)
                print(f"[PERSIST] User buffer now has {len(user_message_buffer)} message(s)")
            except Exception as e:
                print(f"[PERSIST ERROR] Failed to buffer user message: {e}")
                traceback.print_exc()
                
        print("[INIT] Registering event handlers...")
        
        @agent_session.on("user_input_transcribed")
        def on_user_input(event):
            print(f"[EVENT] user_input_transcribed fired")
            is_final = getattr(event, "is_final", False)
            print(f"[EVENT] is_final={is_final}")
            if is_final:
                txt = getattr(event, "transcript", None) or getattr(event, "text", None)
                print(f"[EVENT] User final transcript: {txt}")
                if txt:
                    task = asyncio.create_task(persist_user_message(txt))
                    # Store task reference to prevent garbage collection
                    task.add_done_callback(lambda t: None)
            else:
                print(f"[EVENT] User interim transcript (not saved)")
                
        print("[INIT] Event handlers registered")
        
        try:
            # Disable audio filtering to avoid "audio filter is not found" error
            # The APM (Audio Processing Module) is not available in this LiveKit setup
            # TODO: Install APM module or use alternative audio filtering if needed
            # noise_opts = lk_rtc.NoiseCancellationOptions(
            #     module_id="apm",
            #     options={
            #         "echo_cancellation": True,
            #         "noise_suppression": True,
            #         "auto_gain_control": False,
            #         "high_pass_filter": False,
            #     },
            # )
            # room_input_options = RoomInputOptions(noise_cancellation=noise_opts)
            print("[INIT] Starting agent session...")
            await agent_session.start(agent=agent, room=ctx.room)
            print("[INIT] ✅ Agent session started successfully! Ready for conversation.")
            stop_event = asyncio.Event()
            await stop_event.wait()
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            try:
                await agent_session.aclose()
            finally:
                # Save any remaining user messages in the buffer
                if 'session_manager' in locals() and user_message_buffer:
                    concatenated_user_message = " ".join(user_message_buffer)
                    print(f"[FINALIZE] Saving remaining buffered user messages: {concatenated_user_message[:100]}...")
                    session_manager.buffer_message("user", concatenated_user_message)
                    user_message_buffer.clear()
                
                if 'session_manager' in locals():
                    await asyncio.shield(session_manager.finalize_session())
                
                if 'db' in locals():
                    await db.__aexit__(None, None, None)
                    print("[FINALIZE] DB session closed")
    except Exception as e:
        print("entrypoint exception:", e)
        traceback.print_exc()
        raise

async def _run_agent_server():
    server = AgentServer.from_server_options(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            port=0,
        )
    )
    parent_pid = os.getppid()
    run_task = asyncio.create_task(server.run())
    watch_task = asyncio.create_task(_watch_parent(parent_pid, run_task))
    try:
        await run_task
    except (asyncio.CancelledError, KeyboardInterrupt, GeneratorExit):
        pass
    finally:
        watch_task.cancel()
        await _close_http_ctx()


def run_worker():
    asyncio.run(_run_agent_server())

if __name__ == "__main__":
    run_worker()
