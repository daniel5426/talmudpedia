from typing import Any, Dict, List

from langchain_core.callbacks.manager import adispatch_custom_event

from app.agent.components.retrieval.vector import VectorRetriever
from app.agent.core.interfaces import Tool


class RetrievalTool(Tool):
    """
    Tool for retrieving relevant sources from the vector store.
    The LLM can call this tool multiple times with different queries.
    """

    name = "retrieve_sources"
    description = (
        "Search Rabbinic texts for relevant information. "
        "Use this when you need specific textual sources to answer the question. "
        "You can call this multiple times with different queries if needed."
    )

    def __init__(self, retriever: VectorRetriever):
        self.retriever = retriever

    async def execute(self, query: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute retrieval with the given query.
        
        Args:
            query: The search query to find relevant texts
            
        Returns:
            Dictionary containing:
                - context: Formatted context string
                - documents: List of retrieved documents with metadata
        """
        # Emit retrieval start event
        await adispatch_custom_event(
            "reasoning_step",
            {
                "step": "Retrieval",
                "status": "active",
                "message": f"Searching for: {query}"
            },
        )

        # Perform retrieval
        docs = await self.retriever.retrieve(query)

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

        # Emit retrieval complete event
        await adispatch_custom_event(
            "reasoning_step",
            {
                "step": "Retrieval",
                "status": "complete",
                "message": f"Found {len(docs)} relevant sources"
            },
        )

        return {
            "context": context,
            "documents": retrieved_docs_data,
            "query": query
        }

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the tool schema for function calling.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to find relevant texts"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
