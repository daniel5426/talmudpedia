import os
import json
import asyncio
from pathlib import Path
from typing import TypedDict, Annotated, List, Dict, Any

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END, add_messages
from openai import AsyncOpenAI, Timeout
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Global variables to be set from main
vector_store = None
# Issue #3 Fix: Add timeout configuration (60s total, 10s connect)
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=Timeout(60.0, connect=10.0)
)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    context: str
    retrieved_docs: List[Dict[str, Any]]
    reasoning_items: List[Dict[str, Any]] # Stores encrypted reasoning context

def retrieve(state: AgentState):
    """
    Retrieve relevant context from VectorStore based on the last user message.
    """
    messages = state["messages"]
    last_message = messages[-1]

    context = ""
    retrieved_docs = []

    if vector_store:
        # Simple search based on last message content
        # In a real app, we might want to extract a query first
        results = vector_store.search(last_message.content, limit=5)
        # Format context
        context_parts = []
        for res in results:
            meta = res["metadata"]
            text = meta.get("text", "")
            ref = meta.get("ref", "Unknown Source")
            context_parts.append(f"Source: {ref}\nText: {text}")
            retrieved_docs.append(res)

        context = "\n\n".join(context_parts)

    return {"context": context, "retrieved_docs": retrieved_docs}

async def generate(state: AgentState, config):
    """
    Generate response using OpenAI Responses API with streaming reasoning.
    """
    from langchain_core.callbacks.manager import adispatch_custom_event
    import re
    
    messages = state["messages"]
    context = state.get("context", "")
    previous_reasoning_items = state.get("reasoning_items", [])
    
    system_prompt = (
        "You are a knowledgeable Rabbinic AI assistant. "
        "Use the following retrieved context to answer the user's question. "
        "If the context doesn't contain the answer, rely on your general knowledge but mention that the specific text wasn't found. "
        "Cite your sources clearly based on the context provided.\n\n"
        "Use Markdown formatting for your response.\n\n"
        "If the user's question is not clear, ask for clarification.\n\n"
        "ALWAYS answer in Hebrew.\n\n"
        "ALWAYS provide the reasoning summary in Hebrew.\n\n"
        f"Context:\n{context}"
    )
    
    # Construct input for Responses API
    input_items = []
    
    # Add previous reasoning items first (context persistence)
    if previous_reasoning_items:
        # Sanitize items to remove output-only fields like 'status'
        sanitized_items = []
        for item in previous_reasoning_items:
            clean_item = item.copy()
            if "status" in clean_item:
                del clean_item["status"]
            sanitized_items.append(clean_item)
        input_items.extend(sanitized_items)
        
    # Add system prompt
    input_items.append({
        "role": "user",
        "content": system_prompt
    })
    
    # Add conversation history
    for msg in messages:
        role = "user" if msg.type == "human" else "assistant"
        input_items.append({
            "role": role,
            "content": msg.content
        })
        
    # Call Responses API with streaming
    # Issue #1 Fix: Add comprehensive error logging and event dispatch
    try:
        stream = await client.responses.create(
            model="gpt-5-mini-2025-08-07",
            reasoning={
                "effort": "medium",
                "summary": "auto"
            },
            input=input_items,
            include=["reasoning.encrypted_content"],
            stream=True
        )
    except Exception as e:
        error_msg = f"Failed to create OpenAI stream: {type(e).__name__}: {str(e)}"
        print(f"[AGENT ERROR] {error_msg}")
        # Dispatch error event to frontend
        await adispatch_custom_event(
            "error",
            {"message": error_msg},
            config=config
        )
        raise e
    
    # Process stream
    full_summary = ""
    output_text = ""
    new_reasoning_items = []
    
    # Streaming state
    emitted_steps = {}  # Track what we've emitted: {title: content_length}
    
    # Issue #5 Fix: Add async lock to prevent race conditions in reasoning step updates
    emit_lock = asyncio.Lock()
    
    # Issue #6 Fix: Add stream completion tracking
    stream_completed = False
    
    # Issue #2 Fix: Add error handling for each chunk to prevent silent failures
    async for chunk in stream:
        try:
            # Handle reasoning summary deltas
            if chunk.type == "response.reasoning_summary_text.delta":
                delta = chunk.delta
                full_summary += delta
                
                # Debug: Print the accumulated summary every 100 chars
                if len(full_summary) % 100 < len(delta):
                    print(f"[AGENT] Summary so far ({len(full_summary)} chars): {full_summary[:200]}...")
                
                # Parse for **Title** patterns
                # Find all titles in the accumulated text
                title_pattern = r'\*\*(.*?)\*\*'
                matches = list(re.finditer(title_pattern, full_summary))
                print(f"[AGENT] Matches: {matches}")
                if matches:
                    # We have at least one complete title
                    for i, match in enumerate(matches):
                        title = match.group(1).strip()
                        title_end = match.end()
                        
                        # Find content: from end of this title to start of next title (or end of text)
                        if i + 1 < len(matches):
                            content_end = matches[i + 1].start()
                        else:
                            content_end = len(full_summary)
                        
                        content = full_summary[title_end:content_end].strip()
                        
                        # Remove trailing markdown that matches the next title if present
                        if i + 1 < len(matches):
                            next_title = matches[i + 1].group(1).strip()
                            next_title_markdown = f"**{next_title}**"
                            if content.endswith(next_title_markdown):
                                content = content[:-len(next_title_markdown)].strip()
                            elif content.endswith(f"**{next_title}"):
                                content = content[:-(len(next_title) + 2)].strip()
                        
                        # Debug: Show what we're extracting
                        print(f"[AGENT] Title: '{title}'")
                        print(f"[AGENT] Content boundaries: [{title_end}:{content_end}]")
                        print(f"[AGENT] Content preview: '{content[-100:] if len(content) > 100 else content}'")
                        
                        # Issue #5 Fix: Use async lock to prevent race conditions
                        async with emit_lock:
                            # Check if this is new or updated
                            if title not in emitted_steps or len(content) > emitted_steps.get(title, 0):
                                # Emit this step
                                print(f"[AGENT] Dispatching event: {title[:50]}... ({len(content)} chars)")
                                await adispatch_custom_event(
                                    "reasoning_step",
                                    {
                                        "step": title,
                                        "message": content,
                                        "status": "active" if i == len(matches) - 1 else "complete"
                                    },
                                    config=config
                                )
                                emitted_steps[title] = len(content)
            
            # Handle output text deltas
            elif chunk.type == "response.output_text.delta":
                delta = chunk.delta
                output_text += delta
                
                # Stream each delta to frontend in real-time
                await adispatch_custom_event(
                    "output_delta",
                    {"delta": delta},
                    config=config
                )
            
            # Handle final response
            elif chunk.type == "response.completed":
                # Issue #6 Fix: Mark stream as completed
                stream_completed = True
                # Extract reasoning items from final response
                response_data = chunk.response
                if response_data and hasattr(response_data, 'output'):
                    for item in response_data.output:
                        new_reasoning_items.append(item.model_dump() if hasattr(item, 'model_dump') else dict(item))
        
        except Exception as e:
            # Issue #2 Fix: Log chunk processing errors but continue with other chunks
            print(f"[AGENT ERROR] Error processing chunk type '{chunk.type}': {type(e).__name__}: {str(e)}")
            # Continue processing other chunks instead of crashing
            continue
    
    # Issue #6 Fix: Validate stream completion
    if not stream_completed:
        warning_msg = "Stream ended without completion event"
        print(f"[AGENT WARNING] {warning_msg}")
        await adispatch_custom_event(
            "warning",
            {"message": warning_msg},
            config=config
        )
    
    # Create final message
    from langchain_core.messages import AIMessage
    ai_message = AIMessage(content=output_text)
    
    # Parse final summary into steps for persistence
    reasoning_steps_parsed = []
    if full_summary:
        title_pattern = r'\*\*(.*?)\*\*'
        parts = re.split(f'({title_pattern})', full_summary)
        
        current_title = "Reasoning Summary"
        current_content = ""
        
        if parts and not parts[0].startswith("**"):
            current_content = parts[0].strip()
            parts = parts[1:]
        
        i = 0
        while i < len(parts):
            if i + 1 < len(parts) and parts[i].startswith("**"):
                # Extract title
                title_match = re.match(r"\*\*(.*?)\*\*", parts[i])
                if title_match:
                    if current_content:
                        reasoning_steps_parsed.append({
                            "title": current_title,
                            "content": current_content
                        })
                    current_title = title_match.group(1).strip()
                    current_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
                i += 2
            else:
                i += 1
        
        if current_content:
            reasoning_steps_parsed.append({
                "title": current_title,
                "content": current_content
            })
    
    if not reasoning_steps_parsed and full_summary:
        reasoning_steps_parsed.append({
            "title": "Reasoning Summary",
            "content": full_summary
        })
    
    return {
        "messages": [ai_message], 
        "reasoning_items": new_reasoning_items,
        "reasoning_steps_parsed": reasoning_steps_parsed
    }

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("generate", generate)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

agent = workflow.compile()


