from app.agent.components.llm.openai import OpenAILLM
from app.agent.components.retrieval.vector import VectorRetriever
from app.agent.config import AgentConfig
from app.agent.core.base import BaseAgent
from app.agent.workflows.simple_rag import SimpleRAGWorkflow
from app.agent.workflows.advanced_rag import AdvancedRAGWorkflow


class AgentFactory:
    """
    Factory to create agents based on configuration.
    """

    @staticmethod
    def create_agent(config: AgentConfig) -> BaseAgent:
        """
        Create an agent instance.
        """
        # Create LLM
        if config.llm.provider == "openai":
            llm = OpenAILLM(
                model=config.llm.model,
                api_key=config.llm.api_key
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {config.llm.provider}")

        # Create Retriever
        if config.retrieval.provider == "vector":
            retriever = VectorRetriever(
                index_name=config.retrieval.index_name,
                limit=config.retrieval.limit
            )
        else:
            raise ValueError(f"Unsupported retrieval provider: {config.retrieval.provider}")

        # Create Workflow
        if config.workflow == "simple_rag":
            return SimpleRAGWorkflow(llm=llm, retriever=retriever)
        elif config.workflow == "advanced_rag":
            return AdvancedRAGWorkflow(llm=llm, retriever=retriever)
        else:
            raise ValueError(f"Unsupported workflow: {config.workflow}")
