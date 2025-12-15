import { useState, useRef, useCallback, useEffect } from 'react';

type LiveTextMessage = {
    role: 'user' | 'assistant';
    content: string;
    is_final?: boolean;
}

type LiveToolMessage = {
    tool: string;
    status?: string;
    query?: string;
    citations?: Array<{
        title: string;
        url: string;
        description: string;
        sourceRef?: string;
        ref?: string;
    }>;
}

export const useGeminiLive = (
    url: string,
    onChatCreated?: (id: string) => void,
    onLiveText?: (msg: LiveTextMessage) => void,
    onLiveTool?: (msg: LiveToolMessage) => void
) => {
    const [isConnected, setIsConnected] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const ws = useRef<WebSocket | null>(null);
    const audioContext = useRef<AudioContext | null>(null);
    const outputAudioContext = useRef<AudioContext | null>(null);
    const audioWorkletNode = useRef<AudioWorkletNode | null>(null);
    const stream = useRef<MediaStream | null>(null);
    const nextStartTime = useRef(0);
    const scheduledSources = useRef<Set<AudioBufferSourceNode>>(new Set());
    const lastBargeInMs = useRef(0);
    const onChatCreatedRef = useRef(onChatCreated);
    const [analyserNode, setAnalyserNode] = useState<AnalyserNode | null>(null);

    useEffect(() => {
        onChatCreatedRef.current = onChatCreated;
    }, [onChatCreated]);

    const stopRecording = useCallback(() => {
        stream.current?.getTracks().forEach(track => track.stop());
        stream.current = null;
        if (audioContext.current) {
            audioContext.current.close();
            audioContext.current = null;
        }
        setAnalyserNode(null);
        setIsRecording(false);
    }, []);

    const playAudio = useCallback((base64Data: string) => {
        if (!outputAudioContext.current) {
            outputAudioContext.current = new (window.AudioContext || (window as any).webkitAudioContext)({
                sampleRate: 24000,
            });
        }
        
        if (outputAudioContext.current.state === 'suspended') {
            outputAudioContext.current.resume();
        }

        const binaryString = atob(base64Data);
        const len = binaryString.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        const int16Array = new Int16Array(bytes.buffer);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
            float32Array[i] = int16Array[i] / 32768.0;
        }

        const buffer = outputAudioContext.current.createBuffer(1, float32Array.length, 24000);
        buffer.getChannelData(0).set(float32Array);

        const source = outputAudioContext.current.createBufferSource();
        source.buffer = buffer;
        source.connect(outputAudioContext.current.destination);
        scheduledSources.current.add(source);
        source.onended = () => {
            scheduledSources.current.delete(source);
        };
        
        const now = outputAudioContext.current.currentTime;
        const start = Math.max(now, nextStartTime.current);
        source.start(start);
        nextStartTime.current = start + buffer.duration;
    }, []);

    const stopOutputAudio = useCallback(() => {
        const ctx = outputAudioContext.current;
        if (!ctx) return;
        for (const s of Array.from(scheduledSources.current)) {
            try {
                s.stop();
            } catch {}
        }
        scheduledSources.current.clear();
        nextStartTime.current = ctx.currentTime;
    }, []);

    const connect = useCallback(() => {
        if (ws.current?.readyState === WebSocket.OPEN) return;

        ws.current = new WebSocket(url);

        ws.current.onopen = () => {
            console.log('Connected to Gemini Live');
            setIsConnected(true);
        };

        ws.current.onclose = () => {
            console.log('Disconnected from Gemini Live');
            setIsConnected(false);
            stopRecording();
        };

        ws.current.onerror = (error) => {
            console.error('Gemini Live WebSocket error:', error);
            setIsConnected(false);
        };

        ws.current.onmessage = async (event) => {
            try {
                const message = JSON.parse(event.data);
                if (message.type === 'audio') {
                    playAudio(message.data);
                } else if (message.type === 'interrupted') {
                    stopOutputAudio();
                } else if (message.type === 'live_text') {
                    const role = message.role === 'assistant' ? 'assistant' : 'user';
                    const content = typeof message.content === 'string' ? message.content : '';
                    const isFinal = Boolean(message.is_final);
                    if (content) {
                        onLiveText?.({ role, content, is_final: isFinal });
                    }
                } else if (message.type === 'live_tool') {
                    onLiveTool?.({
                        tool: typeof message.tool === 'string' ? message.tool : 'unknown',
                        status: typeof message.status === 'string' ? message.status : undefined,
                        query: typeof message.query === 'string' ? message.query : undefined,
                        citations: Array.isArray(message.citations) ? message.citations : undefined
                    });
                } else if (message.type === 'setup_complete') {
                    if (message.chat_id) {
                        onChatCreatedRef.current?.(message.chat_id);
                    }
                } else if (message.type === 'text') {
                    // Start of Text Handling from backend
                    // We can expose this if we want to stream text to UI
                    // e.g. onTextReceived(message.content)
                }
            } catch (e) {
                console.error('Error parsing message:', e);
            }
        };
    }, [url, playAudio, stopRecording, onLiveText, onLiveTool]);

    const disconnect = useCallback(() => {
        ws.current?.close();
        ws.current = null;
        stopRecording();
    }, [stopRecording]);

    const startRecording = useCallback(async () => {
        if (!isConnected || !ws.current) return;

        try {
            stream.current = await navigator.mediaDevices.getUserMedia({ audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                autoGainControl: true,
                noiseSuppression: true
            } });

            audioContext.current = new (window.AudioContext || (window as any).webkitAudioContext)({
                sampleRate: 16000,
            });
            
            // Create analyser
            const analyser = audioContext.current.createAnalyser();
            analyser.fftSize = 256;
            setAnalyserNode(analyser);

            // Load worklet for PCM processing
            const blob = new Blob([`
                class PCMProcessor extends AudioWorkletProcessor {
                    process(inputs, outputs, parameters) {
                        const input = inputs[0];
                        if (input && input.length > 0) {
                            const channelData = input[0];
                            this.port.postMessage(channelData);
                        }
                        return true;
                    }
                }
                registerProcessor('pcm-processor', PCMProcessor);
            `], { type: 'application/javascript' });
            
            await audioContext.current.audioWorklet.addModule(URL.createObjectURL(blob));

            const source = audioContext.current.createMediaStreamSource(stream.current);
            audioWorkletNode.current = new AudioWorkletNode(audioContext.current, 'pcm-processor');

            audioWorkletNode.current.port.onmessage = (event) => {
                const float32Array = event.data;
                const outCtx = outputAudioContext.current;
                if (outCtx) {
                    let sum = 0;
                    for (let i = 0; i < float32Array.length; i++) {
                        const v = float32Array[i];
                        sum += v * v;
                    }
                    const rms = Math.sqrt(sum / Math.max(1, float32Array.length));
                    const nowMs = Date.now();
                    if (rms > 0.05 && nextStartTime.current > outCtx.currentTime + 0.08 && nowMs - lastBargeInMs.current > 250) {
                        lastBargeInMs.current = nowMs;
                        stopOutputAudio();
                    }
                }
                // Convert Float32 to Base64 PCM16
                const int16Array = new Int16Array(float32Array.length);
                for (let i = 0; i < float32Array.length; i++) {
                     const s = Math.max(-1, Math.min(1, float32Array[i]));
                     int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                
                let binary = '';
                const bytes = new Uint8Array(int16Array.buffer);
                const len = bytes.byteLength;
                for (let i = 0; i < len; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                const base64Data = btoa(binary);

                if (ws.current?.readyState === WebSocket.OPEN) {
                    ws.current.send(JSON.stringify({
                        type: 'audio',
                        data: base64Data
                    }));
                }
            };

            // Graph: Source -> Analyser -> Worklet -> Destination (mute)
            source.connect(analyser); 
            analyser.connect(audioWorkletNode.current);
            audioWorkletNode.current.connect(audioContext.current.destination);

            setIsRecording(true);
        } catch (error) {
            console.error('Error starting recording:', error);
        }
    }, [isConnected, stopOutputAudio]);

    useEffect(() => {
        return () => {
            disconnect();
            if (outputAudioContext.current) {
                outputAudioContext.current.close();
                outputAudioContext.current = null;
            }
        };
    }, [disconnect]);

    return {
        isConnected,
        isRecording,
        connect,
        disconnect,
        startRecording,
        stopRecording,
        analyser: analyserNode
    };
};
