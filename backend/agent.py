import os
from pathlib import Path
from typing import TypedDict, Annotated, List, Dict, Any

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Global variables to be set from main
vector_store = None
llm = ChatOpenAI(
    model="gpt-5.1-2025-11-13",
    temperature=1,
    reasoning_effort="medium",
    openai_api_key=os.getenv("OPENAI_API_KEY")
)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    context: str
    retrieved_docs: List[Dict[str, Any]]

def retrieve(state: AgentState):
    """
    Retrieve relevant context from VectorStore based on the last user message.
    """
    messages = state["messages"]
    last_message = messages[-1]

    context = ""
    retrieved_docs = []

    if vector_store:
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

def generate(state: AgentState):
    """
    Generate response using LLM and context.
    """
    messages = state["messages"]
    context = state.get("context", "")
    
    system_prompt = (
        "You are a knowledgeable Rabbinic AI assistant. "
        "Use the following retrieved context to answer the user's question. "
        "If the context doesn't contain the answer, rely on your general knowledge but mention that the specific text wasn't found. "
        "Cite your sources clearly based on the context provided.\n\n"
        f"Context:\n{context}"
    )
    
    # Prepend system message or update the first message if it's already a system message
    # For simplicity in this graph, we'll just pass it as a system message in the generation call
    # but LangChain expects a list.
    
    # We need to construct the full prompt.
    # We can't easily modify the 'messages' state in place for just this call without affecting history,
    # so we construct a temporary list for the LLM.
    
    prompt_messages = [SystemMessage(content=system_prompt)] + messages
    
    response = llm.invoke(prompt_messages)
    return {"messages": [response]}

# Build Graph
workflow = StateGraph(AgentState)
workflow.add_node("retrieve", retrieve)
workflow.add_node("generate", generate)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "generate")
workflow.add_edge("generate", END)

agent = workflow.compile()
