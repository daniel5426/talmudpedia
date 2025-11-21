'use client';

import React, { useState, useRef, useEffect } from 'react';
import type { FileUIPart } from 'ai';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
import { convertToHebrew } from '@/lib/hebrewUtils';
import { api } from '@/lib/api';
import { Conversation, ConversationContent, ConversationEmptyState, ConversationScrollButton } from '@/components/ai-elements/conversation';
import {
  Message,
  MessageContent,
  MessageResponse,
  MessageActions,
  MessageAction,
  MessageAttachments,
  MessageAttachment
} from '@/components/ai-elements/message';
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputBody,
  PromptInputFooter,
  PromptInputTools,
  PromptInputActionMenu,
  PromptInputActionMenuTrigger,
  PromptInputActionMenuContent,
  PromptInputActionAddAttachments,
  PromptInputButton,
  PromptInputProvider,
  PromptInputAttachments,
  PromptInputAttachment as NewPromptInputAttachment,
  PromptInputSubmit,
  PromptInputSpeechButton
} from '@/components/ai-elements/prompt-input';
import {
    InlineCitation,
    InlineCitationCard,
    InlineCitationCardTrigger,
    InlineCitationCardBody,
    InlineCitationSource
} from '@/components/ai-elements/inline-citation';
import { ChainOfThought, ChainOfThoughtHeader, ChainOfThoughtContent, ChainOfThoughtStep } from '@/components/ai-elements/chain-of-thought';
import {  CopyIcon, RefreshCcwIcon, ThumbsUpIcon, ThumbsDownIcon, GlobeIcon, BrainIcon, SearchIcon, DatabaseIcon } from 'lucide-react';
import { nanoid } from 'nanoid';
import Image from 'next/image';

  interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    createdAt: Date;
    attachments?: FileUIPart[];
    citations?: Array<{ title: string; url: string; description: string }>;
    reasoningSteps?: Array<{ label: string; status: 'active' | 'complete' | 'pending'; icon: any; description?: string; citations?: Array<{ title: string; url: string; description: string }> }>;
  }

  const RTL_TEXT_CLASS = 'text-right';

  export function ChatPane() {
    const { setSourceListOpen, activeChatId, setActiveChatId } = useLayoutStore();
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [streamingContent, setStreamingContent] = useState("");
    const [currentCitations, setCurrentCitations] = useState<ChatMessage['citations']>([]);
    const [currentReasoning, setCurrentReasoning] = useState<ChatMessage['reasoningSteps']>([]);
    
    const [liked, setLiked] = useState<Record<string, boolean>>({});
    const [disliked, setDisliked] = useState<Record<string, boolean>>({});

    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const citationsRef = useRef<ChatMessage['citations']>([]);
    const reasoningRef = useRef<ChatMessage['reasoningSteps']>([]);
    const abortControllerRef = useRef<AbortController | null>(null);
    const isInitializingChatRef = useRef(false);

    // Load chat history when activeChatId changes
    useEffect(() => {
      async function loadHistory() {
        // If we are initializing a new chat from a response, don't abort the current request
        if (isInitializingChatRef.current) {
            isInitializingChatRef.current = false;
            return;
        }

        // Abort any ongoing request when switching chats
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }

        if (!activeChatId) {
          setMessages([]);
          return;
        }
        
        try {
          const history = await api.getChatHistory(activeChatId);
          const formattedMessages: ChatMessage[] = history.messages.map((msg) => ({
            id: nanoid(),
            role: msg.role,
            content: msg.content,
            createdAt: new Date(), // In a real app, use msg.created_at
            citations: msg.citations,
            reasoningSteps: msg.reasoning_steps ? msg.reasoning_steps.map((step: any) => ({
                label: step.step,
                status: step.status,
                icon: step.step === 'Retrieval' ? SearchIcon : (step.step === 'Analysis' ? BrainIcon : DatabaseIcon),
                description: step.message,
                citations: step.citations
            })) : undefined
          }));
          setMessages(formattedMessages);
        } catch (error) {
          console.error("Failed to load chat history", error);
        }
      }
      loadHistory();
    }, [activeChatId]);

    const handleSubmit = async (message: { text: string; files: FileUIPart[] }) => {
      console.log("handleSubmit called", message);
      if (!message.text.trim() && message.files.length === 0) return;

        const userMessage: ChatMessage = {
        id: nanoid(),
        role: 'user',
        content: message.text,
        createdAt: new Date(),
        attachments: message.files
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setStreamingContent("");
      setCurrentCitations([]);
      setCurrentReasoning([]);

      citationsRef.current = [];
      reasoningRef.current = [];

      try {
        // Abort previous request if exists (though should be handled by useEffect, good safety)
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        console.log("sending fetch");
        const response = await fetch('/api/py/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: message.text,
            chatId: activeChatId
          }),
          signal: abortController.signal
        });
        console.log("fetch done", response.status);

        if (!response.ok) throw new Error('Chat request failed');
        
        // Check for new chat ID header if we started a new chat
        const newChatId = response.headers.get('X-Chat-ID');
        if (newChatId && newChatId !== activeChatId) {
          isInitializingChatRef.current = true;
          setActiveChatId(newChatId);
        }

        const reader = response.body?.getReader();
        if (!reader) return;

        let aiContent = "";
        const decoder = new TextDecoder();
        let buffer = "";
        
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (abortController.signal.aborted) {
              reader.cancel();
              break;
          }
          
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || ""; // Keep the last incomplete line in buffer

          for (const line of lines) {
            if (!line.trim()) continue;
            try {
              const event = JSON.parse(line);
              
              if (event.type === 'token') {
                aiContent += event.content;
                setStreamingContent(aiContent);
              } else if (event.type === 'citation') {
                const newCitation = event.data;
                setCurrentCitations(prev => {
                    const next = [...(prev || []), newCitation];
                    citationsRef.current = next;
                    return next;
                });
              } else if (event.type === 'reasoning') {
                 // Map backend reasoning to frontend format
                 const stepData = event.data;
                 const step = {
                     label: stepData.step,
                     status: stepData.status,
                     icon: stepData.step === 'Retrieval' ? SearchIcon : (stepData.step === 'Analysis' ? BrainIcon : DatabaseIcon),
                     description: stepData.message,
                     citations: stepData.citations
                 };
                 
                 setCurrentReasoning(prev => {
                     const existing = prev || [];
                     // Update existing step if label matches, else add new
                     const index = existing.findIndex(s => s.label === step.label);
                     let newSteps;
                     if (index !== -1) {
                         newSteps = [...existing];
                         newSteps[index] = { ...newSteps[index], ...step };
                     } else {
                         newSteps = [...existing, step];
                     }
                     reasoningRef.current = newSteps;
                     return newSteps;
                 });
              }
            } catch (e) {
              console.error("Error parsing JSON stream line:", line, e);
            }
          }
        }

        // Finalize message
        const aiMessage: ChatMessage = {
          id: nanoid(),
          role: 'assistant',
          content: aiContent,
          createdAt: new Date(),
          citations: citationsRef.current,
          reasoningSteps: reasoningRef.current
        };
        
        setMessages((prev) => [...prev, aiMessage]);
        setStreamingContent("");
        setCurrentCitations([]);
        setCurrentReasoning([]);

      } catch (error: any) {
        if (error.name === 'AbortError') {
            console.log("Request aborted");
            return;
        }
        console.error("Chat error:", error);
      } finally {
        // Only clear loading state if this is the current controller
        if (abortControllerRef.current?.signal.aborted) {
             // If aborted, we might want to keep loading false, but ensure we don't mess up state
             // Actually if aborted, we just stop.
        } else {
             setIsLoading(false);
             abortControllerRef.current = null;
        }
      }
    };
    
    const handleCopy = (content: string) => {
      navigator.clipboard.writeText(content);
    };

    const handleRetry = () => {
      console.log("Retrying...");
    };

    return (
      <div className={`flex flex-col h-full max-w-3xl ${RTL_TEXT_CLASS} mx-auto w-full bg-background p-6`}>
        <Conversation>
          <ConversationContent dir="rtl">
            {messages.length === 0 ? (
              <ConversationEmptyState
                icon={<Image src="/kesher.png" alt="Kesher" width={48} height={48} className="h-12 w-12 text-muted-foreground/50" />}
                title="ברוך הבה לקשר"
                description="המקום שבו אפשר לחפש ולעיין בכל התורה כולה במשפט אחד"
              />
            ) : (
              messages.map((msg) => (
                <Message
                  key={msg.id}
                  from={msg.role}
                  className={`max-w-3xl w-full ${msg.role === 'user' ? 'mr-auto' : 'ml-auto'}`}
                >
                  {msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
                      <MessageAttachments className="mb-2">
                        {msg.attachments.map((attachment) => (
                            <MessageAttachment data={attachment} key={attachment.url || nanoid()} />
                        ))}
                      </MessageAttachments>
                  )}

                  <MessageContent>
                    {msg.role === 'assistant' ? (
                        <>
                            {/* Reasoning Steps (Above Text) */}
                            {msg.reasoningSteps && msg.reasoningSteps.length > 0 && (
                                <div className=" space-y-2">
                                    <ChainOfThought className="text-right" dir="rtl" defaultOpen={true}>
                                        <ChainOfThoughtHeader dir="rtl">שרשרת חישובים ופעולות</ChainOfThoughtHeader>
                                        <ChainOfThoughtContent>
                                            {msg.reasoningSteps.map((step, idx) => (
                                                <ChainOfThoughtStep key={idx} label={step.label} status={step.status as any} icon={step.icon}>
                                                    <div className="text-xs text-muted-foreground">{step.description}</div>
                                                    {step.citations && step.citations.length > 0 && (
                                                        <div className="mt-2">
                                                            <InlineCitation>
                                                                <InlineCitationCard>
                                                                    <InlineCitationCardTrigger 
                                                                        sources={step.citations.map(c => c.url)} 
                                                                        onClick={() => setSourceListOpen(true)}
                                                                    />
                                                                    <InlineCitationCardBody>
                                                                        {step.citations.map((citation, cIdx) => (
                                                                            <InlineCitationSource 
                                                                                key={cIdx}
                                                                                title={convertToHebrew(citation.title)} 
                                                                                sourceRef={citation.title}
                                                                                url={citation.url} 
                                                                                description={citation.description} 
                                                                                className="p-4" 
                                                                            />
                                                                        ))}
                                                                    </InlineCitationCardBody>
                                                                </InlineCitationCard>
                                                            </InlineCitation>
                                                        </div>
                                                    )}
                                                </ChainOfThoughtStep>
                                            ))}
                                        </ChainOfThoughtContent>
                                    </ChainOfThought>
                                </div>
                            )}

                            <div className="text-right" dir="rtl">
                                <MessageResponse>
                                    {msg.content}
                                </MessageResponse>
                            </div>
                            
                            {/* Citations */}
                            {msg.citations && msg.citations.length > 0 && (
                                <div className="mt-1">
                                    <InlineCitation>
                                        <InlineCitationCard>
                                            <InlineCitationCardTrigger 
                                                sources={msg.citations.map(c => c.url)} 
                                                onClick={() => setSourceListOpen(true)}
                                            />
                                            <InlineCitationCardBody>
                                                {msg.citations.map((citation, idx) => (
                                                    <InlineCitationSource 
                                                        key={idx}
                                                        title={convertToHebrew(citation.title)} 
                                                        sourceRef={citation.title}
                                                        url={citation.url} 
                                                        description={citation.description} 
                                                        className="p-4" 
                                                    />
                                                ))}
                                            </InlineCitationCardBody>
                                        </InlineCitationCard>
                                    </InlineCitation>
                                </div> 
                            )}
                        </>
                    ) : (
                        <div className="text-right" dir="rtl">{msg.content}</div>
                    )}
                  </MessageContent>
                  
                  {msg.role === 'assistant' && (
                    <MessageActions>
                        <MessageAction
                          label="Retry"
                          onClick={handleRetry}
                          tooltip="Regenerate response"
                        >
                          <RefreshCcwIcon className="size-4" />
                        </MessageAction>
                        <MessageAction
                          label="Like"
                          onClick={() =>
                            setLiked((prev) => ({
                              ...prev,
                              [msg.id]: !prev[msg.id],
                            }))
                          }
                          tooltip="Like this response"
                        >
                          <ThumbsUpIcon
                            className="size-4"
                            fill={liked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Dislike"
                          onClick={() =>
                            setDisliked((prev) => ({
                              ...prev,
                              [msg.id]: !prev[msg.id],
                            }))
                          }
                          tooltip="Dislike this response"
                        >
                          <ThumbsDownIcon
                            className="size-4"
                            fill={disliked[msg.id] ? "currentColor" : "none"}
                          />
                        </MessageAction>
                        <MessageAction
                          label="Copy"
                          onClick={() => handleCopy(msg.content || "")}
                          tooltip="Copy to clipboard"
                        >
                          <CopyIcon className="size-4" />
                        </MessageAction>
                    </MessageActions>
                  )}
                </Message>
              ))
            )}
            {isLoading && (
               <Message from="assistant" className="max-w-3xl mx-auto w-full">
                  <MessageContent>
                      {/* Streaming Reasoning */}
                      {currentReasoning && currentReasoning.length > 0 && (
                          <div className="mb-1 space-y-4">
                              <ChainOfThought defaultOpen={true}>
                                  <ChainOfThoughtHeader>שרשרת חישובים ופעולות</ChainOfThoughtHeader>
                                  <ChainOfThoughtContent>
                                      {currentReasoning.map((step, idx) => (
                                          <ChainOfThoughtStep key={idx} label={step.label} status={step.status as any} icon={step.icon}>
                                              <div className="text-xs text-muted-foreground">{step.description}</div>
                                              {step.citations && step.citations.length > 0 && (
                                                  <div className="mt-2">
                                                      <InlineCitation>
                                                          <InlineCitationCard>
                                                              <InlineCitationCardTrigger 
                                                                  sources={step.citations.map(c => c.url)} 
                                                                  onClick={() => setSourceListOpen(true)}
                                                              />
                                                              <InlineCitationCardBody>
                                                                  {step.citations.map((citation, cIdx) => (
                                                                      <InlineCitationSource 
                                                                          key={cIdx}
                                                                          title={convertToHebrew(citation.title)} 
                                                                          sourceRef={citation.title}
                                                                          url={citation.url} 
                                                                          description={citation.description} 
                                                                          className="p-4" 
                                                                      />
                                                                  ))}
                                                              </InlineCitationCardBody>
                                                          </InlineCitationCard>
                                                      </InlineCitation>
                                                  </div>
                                              )}
                                          </ChainOfThoughtStep>
                                      ))}
                                  </ChainOfThoughtContent>
                              </ChainOfThought>
                          </div>
                      )}

                      <div className="text-right" dir="rtl">
                          <MessageResponse>
                              {streamingContent}
                          </MessageResponse>
                      </div>
                      
                      {/* Streaming Citations */}
                      {currentCitations && currentCitations.length > 0 && (
                          <div className="mt-1">
                              <InlineCitation>
                                  <InlineCitationCard>
                                      <InlineCitationCardTrigger 
                                          sources={currentCitations.map(c => c.url)} 
                                          onClick={() => setSourceListOpen(true)}
                                      />
                                      <InlineCitationCardBody>
                                          {currentCitations.map((citation, idx) => (
                                              <InlineCitationSource 
                                                  key={idx}
                                                  title={convertToHebrew(citation.title)} 
                                                  sourceRef={citation.title}
                                                  url={citation.url} 
                                                  description={citation.description} 
                                                  className="p-4" 
                                              />
                                          ))}
                                      </InlineCitationCardBody>
                                  </InlineCitationCard>
                              </InlineCitation>
                          </div> 
                      )}
                  </MessageContent>
               </Message>
            )}
          </ConversationContent>
          
          {/* Scroll to Bottom Button - uses Conversation's built-in context */}
          <ConversationScrollButton />
        </Conversation>

        {/* Fixed Input Area */}
        <div dir="rtl" className={`mt-4 w-full max-w-3xl mx-auto ${RTL_TEXT_CLASS}`}>
          <PromptInputProvider>
              <PromptInput onSubmit={handleSubmit} className={`relative ${RTL_TEXT_CLASS}`}>
                  <PromptInputAttachments>
                      {(attachment) => <NewPromptInputAttachment data={attachment} />}
                  </PromptInputAttachments>
                  <PromptInputBody>
                      <PromptInputTextarea ref={textareaRef} className={RTL_TEXT_CLASS} />
                  </PromptInputBody>
                  <PromptInputFooter>
                      <PromptInputTools>
                          <PromptInputActionMenu>
                              <PromptInputActionMenuTrigger />
                              <PromptInputActionMenuContent>
                                  <PromptInputActionAddAttachments />
                              </PromptInputActionMenuContent>
                          </PromptInputActionMenu>
                          <PromptInputSpeechButton textareaRef={textareaRef} />
                          <PromptInputButton>
                              <GlobeIcon size={16} />
                              <span>Search</span>
                          </PromptInputButton>
                      </PromptInputTools>
                      <PromptInputSubmit />
                  </PromptInputFooter>
              </PromptInput>
          </PromptInputProvider>
        </div>
      </div>
    );
  }
