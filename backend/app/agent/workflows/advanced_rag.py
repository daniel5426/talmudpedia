import asyncio
import json
import re
from typing import Any, Dict, List, Literal, Optional

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.retrieval.vector import VectorRetriever
from app.agent.components.tools.retrieval_tool import RetrievalTool
from app.agent.core.base import BaseAgent
from app.agent.core.state import AgentState


class AdvancedRAGWorkflow(BaseAgent):
    """
    Advanced RAG workflow with intelligent retrieval.
    The agent decides when to retrieve based on the query,
    avoiding unnecessary RAG for greetings and simple queries.
    """

    def __init__(self, llm: OpenAILLM, retriever: VectorRetriever):
        super().__init__()
        self.llm = llm
        self.retriever = retriever
        self.retrieval_tool = RetrievalTool(retriever)

    def build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        # Add nodes - simpler structure like SimpleRAG
        # Note: Node is named "retrieve" to match endpoint expectations
        workflow.add_node("retrieve", self.decide_and_retrieve)
        workflow.add_node("generate", self.generate)
        
        # Set entry point
        workflow.set_entry_point("retrieve")
        
        # Linear flow: retrieve → generate → END
        workflow.add_edge("retrieve", "generate")
        workflow.add_edge("generate", END)
        
        return workflow

    async def decide_and_retrieve(self, state: AgentState, config):
        """
        Decide if retrieval is needed and perform it if necessary.
        """
        messages = state["messages"]
        last_message = messages[-1]
        query = last_message.content if isinstance(last_message.content, str) else str(last_message.content)
        
        # Extract text from complex content
        if isinstance(query, list):
            text_parts = [p["text"] for p in query if p.get("type") == "text"]
            query = " ".join(text_parts)
        
        # Emit initial analysis
        await adispatch_custom_event(
            "reasoning_step",
            {"step": "Analysis", "status": "active", "message": "Analyzing your question..."},
            config=config
        )
        
        # Decide if we should retrieve
        should_retrieve = self._should_retrieve(query)
        
        if should_retrieve:
            # Mark analysis as complete
            await adispatch_custom_event(
                "reasoning_step",
                {"step": "Analysis", "status": "complete", "message": ""},
                config=config
            )
            
            # Perform retrieval
            await adispatch_custom_event(
                "reasoning_step",
                {"step": "Retrieval", "status": "active", "message": "Searching Rabbinic texts..."},
                config=config
            )
            
            docs = await self.retriever.retrieve(str(query))
            
            # Format context
            context_parts = []
            retrieved_docs_data = []
            
            for doc in docs:
                ref = doc.metadata.get("ref", "Unknown Source")
                text = doc.content
                context_parts.append(f"Source: {ref}\nText: {text}")
                
                # Prepare doc data for frontend
                doc_data = {
                    "metadata": doc.metadata,
                    "score": doc.score
                }
                retrieved_docs_data.append(doc_data)
            
            context = "\n\n".join(context_parts)
            
            return {
                "context": context,
                "retrieved_docs": retrieved_docs_data,
                "query": str(query)
            }
        else:
            # No retrieval needed - mark analysis as complete
            await adispatch_custom_event(
                "reasoning_step",
                {"step": "Analysis", "status": "complete", "message": ""},
                config=config
            )
            
            return {
                "context": "",
                "retrieved_docs": [],
                "query": str(query)
            }

    def _should_retrieve(self, query: str) -> bool:
        """
        Decide if we should retrieve based on the query.
        Simple heuristic - can be enhanced with LLM decision.
        """
        query_lower = query.lower().strip()
        
        # Greetings and simple phrases
        greetings = ["hi", "hello", "hey", "שלום", "היי", "הי", "מה קורה", "מה נשמע"]
        if any(greeting in query_lower for greeting in greetings):
            return False
            
        # Very short queries
        if len(query.strip()) < 5:
            return False
            
        return True

    async def generate(self, state: AgentState, config):
        """
        Generate response with streaming reasoning.
        """
        messages = state["messages"]
        context = state.get("context", "")
        previous_reasoning_items = state.get("reasoning_items", [])
        files = state.get("files", [])
        
        system_prompt = (
            "You are a knowledgeable Rabbinic AI assistant. "
        )
        
        if context:
            system_prompt += (
                "Use the following retrieved context to answer the user's question. "
                "If the context doesn't contain the answer, rely on your general knowledge but mention that the specific text wasn't found. "
                "Cite your sources clearly based on the context provided.\n\n"
                "Use Markdown formatting for your response.\n\n"
                "If the user's question is not clear, ask for clarification.\n\n"
                "ALWAYS answer in Hebrew.\n\n"
                "ALWAYS provide the reasoning summary in Hebrew.\n\n"
                f"Context:\n{context}"
            )
        else:
            system_prompt += (
                "Answer the user's question based on your knowledge. "
                "Use Markdown formatting for your response.\n\n"
                "ALWAYS answer in Hebrew.\n\n"
                "ALWAYS provide the reasoning summary in Hebrew.\n"
            )

        # Stream from LLM
        stream = self.llm.stream(
            messages=messages,
            system_prompt=system_prompt,
            reasoning_items=previous_reasoning_items,
        )
        
        full_summary = ""
        output_text = ""
        new_reasoning_items = []
        emitted_steps = {}
        emit_lock = asyncio.Lock()
        stream_completed = False

        try:
            async for chunk in stream:
                # Handle reasoning summary deltas
                if chunk.type == "response.reasoning_summary_text.delta":
                    delta = chunk.delta
                    full_summary += delta
                    
                    # Parse for **Title** patterns
                    title_pattern = r'\*\*(.*?)\*\*'
                    matches = list(re.finditer(title_pattern, full_summary))
                    
                    if matches:
                        for i, match in enumerate(matches):
                            title = match.group(1).strip()
                            title_end = match.end()
                            
                            if i + 1 < len(matches):
                                content_end = matches[i + 1].start()
                            else:
                                content_end = len(full_summary)
                            
                            content = full_summary[title_end:content_end].strip()
                            
                            # Cleanup trailing markdown
                            if i + 1 < len(matches):
                                next_title = matches[i + 1].group(1).strip()
                                next_title_markdown = f"**{next_title}**"
                                if content.endswith(next_title_markdown):
                                    content = content[:-len(next_title_markdown)].strip()
                                elif content.endswith(f"**{next_title}"):
                                    content = content[:-(len(next_title) + 2)].strip()

                            async with emit_lock:
                                if title not in emitted_steps or len(content) > emitted_steps.get(title, 0):
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

                elif chunk.type == "response.output_text.delta":
                    delta = chunk.delta
                    output_text += delta
                    await adispatch_custom_event("output_delta", {"delta": delta}, config=config)

                elif chunk.type == "response.completed":
                    stream_completed = True
                    response_data = chunk.response
                    if response_data and hasattr(response_data, 'output'):
                        for item in response_data.output:
                            new_reasoning_items.append(item.model_dump() if hasattr(item, 'model_dump') else dict(item))

        except Exception as e:
            print(f"[AGENT ERROR] {e}")
            # In a real app we might want to re-raise or handle gracefully
            pass

        # Parse final summary for persistence
        reasoning_steps_parsed = self._parse_summary(full_summary)
        
        return {
            "messages": [AIMessage(content=output_text)],
            "reasoning_items": new_reasoning_items,
            "reasoning_steps_parsed": reasoning_steps_parsed
        }

    def _parse_summary(self, full_summary: str) -> List[Dict[str, str]]:
        """Helper to parse the full summary into steps."""
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
            
        return reasoning_steps_parsed
