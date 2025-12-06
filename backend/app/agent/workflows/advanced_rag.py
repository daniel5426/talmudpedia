import os
from typing import Any, Dict, List, Literal, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.retrieval.vector import VectorRetriever
from app.agent.components.tools.retrieval_tool import RetrievalTool
from app.agent.core.base import BaseAgent
from app.agent.core.state import AgentState


class AdvancedRAGWorkflow(BaseAgent):
    """
    Advanced RAG workflow using LangGraph's agent pattern.
    The agent decides when to retrieve based on the query.
    """

    def __init__(self, llm: OpenAILLM, retriever: VectorRetriever):
        super().__init__()
        # We use ChatOpenAI for standard tool calling support
        # We try to use the same model name as the passed llm, or default to gpt-4o
        model_name = getattr(llm, "model", "gpt-4o")
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Initialize Reranker and wrap the retriever
        # Initialize Reranker and wrap the retriever
        from app.agent.components.retrieval.reranker import PineconeReranker
        from app.agent.components.retrieval.lexical import LexicalRetriever
        from app.agent.components.retrieval.hybrid import HybridRetriever
        
        self.reranker = PineconeReranker()
        self.lexical_retriever = LexicalRetriever()
        
        self.retriever = HybridRetriever(
            lexical_retriever=self.lexical_retriever,
            semantic_retriever=retriever,
            reranker=self.reranker,
            lexical_limit=5,
            semantic_limit=20
        )
        
        self.retrieval_tool = RetrievalTool(retriever=self.retriever)
        self.tools = [self.retrieval_tool]
        
        self.model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            streaming=True,
            temperature=0
        ).bind_tools(self.tools)

    def build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)
        
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tools", ToolNode(self.tools))
        
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges(
            "agent",
            tools_condition,
        )
        workflow.add_edge("tools", "agent")
        
        return workflow

    async def call_model(self, state: AgentState, config):
        messages = state["messages"]
        
        # Define system prompt
        system_prompt = (
            "You are a knowledgeable Rabbinic AI assistant. "
            "Search Rabbinic texts for relevant information using the 'retrieve_sources' tool when needed. "
            "ALWAYS use ONLY the retrieved context to answer the user's question. "
            "NEVER answer based on your general knowledge, ONLY based on the retrieved context. "
            "If the context doesn't contain the answer, rely on your general knowledge but mention that the specific text wasn't found. "
            "Cite your sources clearly based on the context provided.\n\n"
            "Use Markdown formatting for your response.\n\n"
            "If the user's question is not clear, ask for clarification.\n\n"
            "ALWAYS answer in Hebrew.\n\n"
            "ALWAYS provide the reasoning summary in Hebrew.\n"
        )
        
        # Ensure system prompt is present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        elif isinstance(messages[0], SystemMessage):
            # Update existing system prompt to ensure our instructions are active
            messages[0] = SystemMessage(content=system_prompt)
            
        response = await self.model.ainvoke(messages, config)
        return {"messages": [response]}
