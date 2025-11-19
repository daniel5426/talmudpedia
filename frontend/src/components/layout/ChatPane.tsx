'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useLayoutStore } from '@/lib/store/useLayoutStore';
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
import { ChainOfThought, ChainOfThoughtHeader, ChainOfThoughtContent, ChainOfThoughtStep, ChainOfThoughtSearchResults, ChainOfThoughtSearchResult } from '@/components/ai-elements/chain-of-thought';
import { Bot, CopyIcon, RefreshCcwIcon, ThumbsUpIcon, ThumbsDownIcon, GlobeIcon, BrainIcon, SearchIcon, DatabaseIcon } from 'lucide-react';
import { nanoid } from 'nanoid';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: Date;
  attachments?: any[];
}

export function ChatPane() {
  const { setSourceListOpen } = useLayoutStore();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  const [liked, setLiked] = useState<Record<string, boolean>>({});
  const [disliked, setDisliked] = useState<Record<string, boolean>>({});

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = async (message: { text: string; files: any[] }) => {
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

    // Simulate AI response
    setTimeout(() => {
      const aiMessage: ChatMessage = {
        id: nanoid(),
        role: 'assistant',
        content: "Here are the sources regarding lighting Chanukah candles. The primary source is the Gemara in Shabbat 21b, which discusses the levels of observance (Mehadrin).",
        createdAt: new Date(),
      };
      setMessages((prev) => [...prev, aiMessage]);
      setIsLoading(false);
      
      setSourceListOpen(true);
    }, 1000);
  };
  
  const handleCopy = (content: string) => {
    navigator.clipboard.writeText(content);
  };

  const handleRetry = () => {
    console.log("Retrying...");
  };

  return (
    <div className="flex flex-col h-full w-full bg-background p-6">
      <Conversation>
        <ConversationContent>
          {messages.length === 0 ? (
            <ConversationEmptyState
              icon={<Bot className="h-12 w-12 text-muted-foreground/50" />}
              title="Ask the Rav"
              description="Ask a question about Halacha, Gemara, or Hashkafa."
            />
          ) : (
            messages.map((msg) => (
              <Message
                key={msg.id}
                from={msg.role}
                className="max-w-3xl mx-auto w-full"
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
                          <MessageResponse>
                              {msg.content}
                          </MessageResponse>
                          {msg.content.includes("Shabbat 21b") && (
                              <div className="mt-1">
                                  <InlineCitation>
                                      <InlineCitationCard>
                                          <InlineCitationCardTrigger sources={["https://talmudpedia.com/shabbat-21b"]} />
                                          <InlineCitationCardBody>
                                              <InlineCitationSource title="Shabbat 21b" url="https://talmudpedia.com/shabbat-21b" description="The primary source for Chanukah laws." className="p-4" />
                                          </InlineCitationCardBody>
                                      </InlineCitationCard>
                                  </InlineCitation>
                              </div> 
                          )}
                      </>
                  ) : (
                      msg.content
                  )}
                  
                  {msg.role === 'assistant' && (
                      <div className="mt-4 space-y-4">
                          <ChainOfThought>
                              <ChainOfThoughtHeader>Detailed Analysis Steps</ChainOfThoughtHeader>
                              <ChainOfThoughtContent>
                                  <ChainOfThoughtStep label="Query Analysis" status="complete" icon={BrainIcon}>
                                      <div className="text-xs text-muted-foreground">Identified key terms: Chanukah, Candles, Halacha.</div>
                                  </ChainOfThoughtStep>
                                  <ChainOfThoughtStep label="Source Retrieval" status="complete" icon={SearchIcon}>
                                      <ChainOfThoughtSearchResults>
                                          <ChainOfThoughtSearchResult>Shabbat 21b</ChainOfThoughtSearchResult>
                                          <ChainOfThoughtSearchResult>Orach Chayim 671</ChainOfThoughtSearchResult>
                                      </ChainOfThoughtSearchResults>
                                  </ChainOfThoughtStep>
                                  <ChainOfThoughtStep label="Synthesis" status="active" icon={DatabaseIcon}>
                                      <div className="text-xs text-muted-foreground">Combining opinions from Rishonim...</div>
                                  </ChainOfThoughtStep>
                              </ChainOfThoughtContent>
                          </ChainOfThought>
                      </div>
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
                    <div className="flex items-center gap-2">
                        <span className="animate-pulse">Thinking...</span>
                    </div>
                </MessageContent>
             </Message>
          )}
        </ConversationContent>
        
        {/* Scroll to Bottom Button - uses Conversation's built-in context */}
        <ConversationScrollButton />
      </Conversation>

      {/* Fixed Input Area */}
      <div className="mt-4 w-full max-w-3xl mx-auto">
        <PromptInputProvider>
            <PromptInput onSubmit={handleSubmit} className="relative">
                <PromptInputAttachments>
                    {(attachment) => <NewPromptInputAttachment data={attachment} />}
                </PromptInputAttachments>
                <PromptInputBody>
                    <PromptInputTextarea ref={textareaRef} />
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
