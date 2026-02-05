from typing import Dict, Type

from app.agent.runtime.base import RuntimeAdapter
from app.agent.runtime.langgraph_adapter import LangGraphAdapter


class RuntimeAdapterRegistry:
    _adapters: Dict[str, Type[RuntimeAdapter]] = {
        "langgraph": LangGraphAdapter,
    }
    _default_name: str = "langgraph"

    @classmethod
    def register(cls, name: str, adapter_cls: Type[RuntimeAdapter]) -> None:
        cls._adapters[name] = adapter_cls

    @classmethod
    def get(cls, name: str) -> Type[RuntimeAdapter]:
        return cls._adapters[name]

    @classmethod
    def get_default(cls) -> Type[RuntimeAdapter]:
        return cls._adapters[cls._default_name]

    @classmethod
    def set_default(cls, name: str) -> None:
        if name not in cls._adapters:
            raise KeyError(f"Runtime adapter '{name}' is not registered")
        cls._default_name = name
