from typing import Any, Dict, List, Type, Optional

from langchain_core.callbacks.manager import (
    AsyncCallbackManagerForToolRun,
    CallbackManagerForToolRun,
    adispatch_custom_event,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, field_validator

from app.agent.core.interfaces import Retriever


class RetrievalInput(BaseModel):
    query: str = Field(description="The search query to find relevant texts")


class RetrievalTool(BaseTool):
    """
    Tool for retrieving relevant sources from the vector store.
    The LLM can call this tool multiple times with different queries.
    """

    name: str = "retrieve_sources"
    description: str = (
        "Search Rabbinic texts for relevant information. "
        "Use this when you need specific textual sources to answer the question. "
        "You can call this multiple times with different queries if needed."
    )
    args_schema: Type[BaseModel] = RetrievalInput
    retriever: Any = Field(exclude=True)

    @field_validator('retriever')
    @classmethod
    def validate_retriever(cls, v: Any) -> Any:
        if not isinstance(v, Retriever):
            raise ValueError(f"retriever must be an instance of Retriever, got {type(v)}")
        return v

    def _run(
        self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> Dict[str, Any]:
        """Synchronous run not implemented."""
        raise NotImplementedError("Use async version")

    async def _arun(
        self, query: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None
    ) -> str:
        """
        Execute retrieval with the given query.
        Returns a string context for the LLM.
        """
        # Emit retrieval start event
        await adispatch_custom_event(
            "retrieval_start",
            {"query": query},
        )
        
        # Add delay to verify independent event dispatch (TESTING ONLY)
        import asyncio
        await asyncio.sleep(1)
        
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
                "score": doc.score,
            }
            retrieved_docs_data.append(doc_data)

        context = "\n\n".join(context_parts)

        # Emit retrieval_complete event with docs and query
        await adispatch_custom_event(
            "retrieval_complete",
            {"docs": retrieved_docs_data, "query": query},
        )

        return context
