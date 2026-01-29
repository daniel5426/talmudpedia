import { useReducer, useCallback, useRef } from 'react';
import { agentService } from '@/services/agent';

// --- Types ---

export type ExecutionStatus = 'idle' | 'running' | 'paused' | 'completed' | 'failed';

export interface ExecutionEvent {
    event: string;
    run_id: string;
    span_id?: string;
    data?: any;
    name?: string;
    tags?: string[];
    visibility?: 'internal' | 'client_safe';
    metadata?: Record<string, any>;
    timestamp: Date;
}

export interface ExecutionState {
    status: ExecutionStatus;
    runId: string | null;
    events: ExecutionEvent[];
    streamingContent: string;
    error: string | null;
}

export interface ExecutionStep {
    id: string;
    name: string;
    type: string;
    status: "pending" | "running" | "completed" | "error";
    input?: any;
    output?: any;
    timestamp: Date;
}

type Action = 
    | { type: 'START_RUN'; runId: string }
    | { type: 'RESUME_RUN' }
    | { type: 'EVENT_RECEIVED'; event: Omit<ExecutionEvent, 'timestamp'> }
    | { type: 'RUN_COMPLETE' }
    | { type: 'RUN_FAILED'; error: string }
    | { type: 'RESET' };

// --- Reducer ---

const initialState: ExecutionState = {
    status: 'idle',
    runId: null,
    events: [],
    streamingContent: "",
    error: null,
};

function executionReducer(state: ExecutionState, action: Action): ExecutionState {
    switch (action.type) {
        case 'START_RUN':
            return {
                ...initialState,
                status: 'running',
                runId: action.runId,
            };
        case 'RESUME_RUN':
            return {
                ...state,
                status: 'running',
                error: null,
            };
        case 'EVENT_RECEIVED': {
            const newEvent = { ...action.event, timestamp: new Date() };
            // Append event
            const newEvents = [...state.events, newEvent];
            
            // Update streaming content if chat model stream (legacy) or explicit token (new)
            let newContent = state.streamingContent;
            if (action.event.event === 'on_chat_model_stream' && action.event.data?.chunk?.content) {
                newContent += action.event.data.chunk.content;
            } else if (action.event.event === 'token' && action.event.data?.content) {
                newContent += action.event.data.content;
            }

            // Sync status from event if present (e.g. run_status)
            let newStatus = state.status;
            if (action.event.event === 'run_status') {
                newStatus = action.event.data?.status || newStatus;
            }
            // Handle error events
            if (action.event.event === 'error') {
                 newStatus = 'failed';
            }

            return {
                ...state,
                status: newStatus as ExecutionStatus,
                events: newEvents,
                streamingContent: newContent,
            };
        }
        case 'RUN_COMPLETE':
             return {
                ...state,
                status: 'completed',
            };
        case 'RUN_FAILED':
            return {
                ...state,
                status: 'failed',
                error: action.error,
            };
        case 'RESET':
            return initialState;
        default:
            return state;
    }
}

// --- Hook ---

export function useAgentExecution() {
    const [state, dispatch] = useReducer(executionReducer, initialState);
    const abortControllerRef = useRef<AbortController | null>(null);

    const stop = useCallback(() => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
    }, []);

    const execute = useCallback(async (agentId: string, input: string, mode: 'debug' | 'production' = 'production', existingRunId?: string) => {
        // 1. Teardown existing
        stop();
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        try {
            // 2. Start / Resume
            let runId = existingRunId;
            if (runId) {
                dispatch({ type: 'RESUME_RUN' });
            } 
            // Note: If no runId, the stream endpoint will create one.
            // However, our reducer expects 'START_RUN' with a runId if possible, or we wait for the first 'run_id' event.
            // For cleaner UI, we might want to call startRun first if not resuming, OR just let the stream handle it.
            // The existing `streamAgent` service handles both.
            
            if (!runId) {
                 // Reset state for new run (will set runId when event arrives)
                 dispatch({ type: 'RESET' });
            }

            // 3. Connect Stream
            // We need to pass the input only if we are starting/resuming with input
             const payload = { 
                text: input,
                runId: runId
            };
            
            // Pass mode as separate arg if service supports it, or as query param
            // Assuming we updated agentService to accept mode options
            const response = await agentService.streamAgent(agentId, payload, mode);
            
            const reader = response.body?.getReader();
            if (!reader) throw new Error("Failed to get stream reader");

            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    const dataStr = line.slice(6).trim();
                    console.log("[useAgentExecution] Received event:", dataStr.slice(0, 50));
                    if (dataStr === "[DONE]") break;

                    try {
                        const eventData = JSON.parse(dataStr);
                        
                        if (eventData.type === 'error') {
                            throw new Error(eventData.error);
                        }
                        if (eventData.type === 'done') break;

                        // Identify Run ID if we didn't have it
                        if (eventData.event === 'run_id') {
                            if (!runId) {
                                runId = eventData.run_id;
                                dispatch({ type: 'START_RUN', runId: eventData.run_id });
                            }
                            continue;
                        }

                        // Dispatch Event
                        dispatch({ type: 'EVENT_RECEIVED', event: eventData });

                    } catch (e) {
                         console.warn("Failed to parse SSE event", e);
                    }
                }
            }
            
            dispatch({ type: 'RUN_COMPLETE' });

        } catch (e: any) {
            if (e.name === 'AbortError') return;
            console.error("Execution failed", e);
            dispatch({ type: 'RUN_FAILED', error: e.message || String(e) });
        } finally {
            abortControllerRef.current = null;
        }
    }, [stop]);

    const getExecutionSteps = useCallback((): ExecutionStep[] => {
        const steps: ExecutionStep[] = [];
        const activeSteps = new Map<string, ExecutionStep>();

        state.events.forEach(event => {
            const isStart = event.event.endsWith('_start');
            const isEnd = event.event.endsWith('_end');
            const type = event.event.includes('tool') ? 'tool' : 'node'; // simple heuristic
            const id = event.span_id || event.run_id || 'unknown';

            if (isStart) {
                const step: ExecutionStep = {
                    id,
                    name: event.name || event.event,
                    type,
                    status: 'running',
                    input: event.data?.input,
                    timestamp: event.timestamp
                };
                activeSteps.set(id, step);
                steps.push(step);
            } else if (isEnd) {
                const step = activeSteps.get(id);
                if (step) {
                    step.status = 'completed';
                    step.output = event.data?.output;
                }
            } else if (event.event === 'error') {
                 const step = activeSteps.get(id) || steps[steps.length - 1]; // fallback to last step
                 if (step) {
                     step.status = 'error';
                     step.output = event.data;
                 }
            }
        });

        return steps;
    }, [state.events]);

    return {
        state,
        execute,
        stop,
        isRunning: state.status === 'running',
        steps: getExecutionSteps()
    };
}
