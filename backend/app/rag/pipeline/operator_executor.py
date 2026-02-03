"""
Operator Executor - Base class and implementations for pipeline operator execution.

This module defines the Operator Contract:
- Every operator must implement the execute() method
- Input/output validation is enforced
- Operators support configuration at runtime
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic
from pydantic import BaseModel
from datetime import datetime
import asyncio
import traceback
import uuid

from app.rag.pipeline.registry import OperatorSpec, DataType
from app.rag.factory import RAGFactory


class OperatorInput(BaseModel):
    """Base input for all operators."""
    data: Any
    metadata: Dict[str, Any] = {}
    source_operator_id: Optional[str] = None


class OperatorOutput(BaseModel):
    """Base output for all operators."""
    data: Any
    metadata: Dict[str, Any] = {}
    operator_id: str
    execution_time_ms: float = 0.0
    success: bool = True
    error_message: Optional[str] = None


class ExecutionContext(BaseModel):
    """Context passed to operators during execution."""
    tenant_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    job_id: Optional[str] = None
    step_id: str
    config: Dict[str, Any] = {}
    secrets: Dict[str, str] = {}  # Resolved secrets
    
    class Config:
        extra = "allow"


class OperatorExecutor(ABC):
    """
    Abstract base class for all operator executors.
    
    This is the "Operator Contract" - every operator must implement this interface.
    Subclasses must implement:
    - execute(): The main execution logic
    - Optionally validate_input() and validate_output() for custom validation
    """
    
    def __init__(self, spec: OperatorSpec):
        self.spec = spec
        self.operator_id = spec.operator_id
    
    @abstractmethod
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        """
        Execute the operator.
        
        Args:
            input_data: The input data from the previous operator
            context: Execution context with config, secrets, and metadata
            
        Returns:
            OperatorOutput with the processed data
        """
        pass
    
    def validate_input(self, input_data: OperatorInput) -> List[str]:
        """
        Validate input data against the operator's input schema.
        
        Returns a list of validation errors (empty if valid).
        """
        errors = []
        
        # Check input type compatibility
        if self.spec.input_type != DataType.NONE:
            if input_data.data is None:
                errors.append(f"Operator {self.operator_id} requires input data")
        
        return errors
    
    def validate_output(self, output_data: OperatorOutput) -> List[str]:
        """
        Validate output data against the operator's output schema.
        
        Returns a list of validation errors (empty if valid).
        """
        errors = []
        
        if self.spec.output_type != DataType.NONE:
            if output_data.data is None:
                errors.append(f"Operator {self.operator_id} must produce output data")
        
        return errors
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate configuration using the operator spec."""
        return self.spec.validate_config(config)

    async def safe_execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        """
        Execute with error handling and timing.
        
        This is the main entry point for executing an operator.
        """
        start_time = datetime.utcnow()
        
        try:
            # Validate input
            input_errors = self.validate_input(input_data)
            if input_errors:
                return OperatorOutput(
                    data=None,
                    operator_id=self.operator_id,
                    success=False,
                    error_message=f"Input validation failed: {'; '.join(input_errors)}"
                )
            
            # Validate config
            config_errors = self.validate_config(context.config)
            if config_errors:
                return OperatorOutput(
                    data=None,
                    operator_id=self.operator_id,
                    success=False,
                    error_message=f"Config validation failed: {'; '.join(config_errors)}"
                )
            
            # Execute
            output = await self.execute(input_data, context)
            
            # Validate output if execution was successful
            if output.success:
                output_errors = self.validate_output(output)
                if output_errors:
                    output.success = False
                    output.error_message = f"Output validation failed: {'; '.join(output_errors)}"
            
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            output.execution_time_ms = execution_time
            
            return output
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            return OperatorOutput(
                data=None,
                operator_id=self.operator_id,
                execution_time_ms=execution_time,
                success=False,
                error_message=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            )


# =============================================================================
# CUSTOM PYTHON OPERATOR
# =============================================================================

class PythonOperatorExecutor(OperatorExecutor):
    """
    Executor for user-defined Python operators.
    
    Users can define custom operators by providing Python code that:
    - Receives input_data (list of documents/chunks/etc.)
    - Receives config (dict of configuration values)
    - Returns processed data
    
    The code should define a function called `process`:
    
    ```python
    def process(input_data: list, config: dict) -> list:
        # Your custom logic here
        result = []
        for item in input_data:
            # Process item
            result.append(processed_item)
        return result
    ```
    """
    
    def __init__(self, spec: OperatorSpec, python_code: str):
        super().__init__(spec)
        self.python_code = python_code
        self._compiled_code = None
        self._namespace: Dict[str, Any] = {}
    
    def _compile_code(self):
        """Compile the Python code and extract the process function."""
        if self._compiled_code is None:
            # Create a restricted namespace
            self._namespace = {
                "__builtins__": {
                    # Allow safe builtins
                    "len": len,
                    "range": range,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "None": None,
                    "True": True,
                    "False": False,
                    "print": print,
                    "isinstance": isinstance,
                    "sorted": sorted,
                    "reversed": reversed,
                    "min": min,
                    "max": max,
                    "sum": sum,
                    "any": any,
                    "all": all,
                    "abs": abs,
                    "round": round,
                },
                # Common imports that are safe
                "re": __import__("re"),
                "json": __import__("json"),
                "datetime": __import__("datetime"),
                "requests": __import__("requests"),
                "time": __import__("time"),
                "random": __import__("random"),
            }
            
            # Compile and execute to define the function
            self._compiled_code = compile(self.python_code, "<custom_operator>", "exec")
            exec(self._compiled_code, self._namespace)
            
            if "execute" not in self._namespace and "process" not in self._namespace:
                raise ValueError("Custom operator code must define an 'execute(context)' or 'process(input_data, config)' function")
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        """Execute the custom Python operator."""
        try:
            self._compile_code()
            
            # Check for modern protocol 'execute(context)'
            if "execute" in self._namespace:
                execute_func = self._namespace["execute"]
                
                # Wrap inputs into a context object as expected by the frontend template
                class CustomContext:
                    def __init__(self, input_data_val, config_val, metadata_val):
                        self.input_data = input_data_val
                        self.config = config_val
                        self.metadata = metadata_val
                
                user_context = CustomContext(input_data.data, context.config, input_data.metadata)
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: execute_func(user_context)
                )
            else:
                # Fallback to legacy 'process(input_data, config)'
                process_func = self._namespace["process"]
                
                # Run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: process_func(input_data.data, context.config)
                )
            
            return OperatorOutput(
                data=result,
                metadata=input_data.metadata,
                operator_id=self.operator_id,
                success=True
            )
            
        except Exception as e:
            return OperatorOutput(
                data=None,
                operator_id=self.operator_id,
                success=False,
                error_message=f"Custom operator error: {str(e)}\n{traceback.format_exc()}"
            )


# =============================================================================
# ARTIFACT-BASED OPERATOR EXECUTOR 
# =============================================================================

class ArtifactContext:
    """The context passed to an artifact's execute(context) function."""
    def __init__(self, input_data: Any, config: Dict[str, Any], metadata: Dict[str, Any] = None):
        self.input_data = input_data
        self.config = config
        self.metadata = metadata or {}


class ArtifactExecutor(OperatorExecutor):

    """
    Executor for artifact-based operators.
    
    Loads and executes operator code from the filesystem using importlib,
    providing a more robust and testable execution model than PythonOperatorExecutor.
    """
    
    def __init__(self, spec: OperatorSpec, artifact_id: str, version: Optional[str] = None):
        super().__init__(spec)
        self.artifact_id = artifact_id
        self.version = version or spec.version
        self._module = None
        self._execute_func = None

    
    def _load_module(self):
        """Load the artifact's handler module dynamically."""
        if self._module is not None:
            return
        
        import importlib
        import importlib.util
        from app.services.artifact_registry import get_artifact_registry
        
        registry = get_artifact_registry()
        artifact_path = registry.get_artifact_path(self.artifact_id, self.version)

        
        if not artifact_path:
            raise ValueError(f"Artifact not found: {self.artifact_id}")
        
        handler_path = artifact_path / "handler.py"
        if not handler_path.exists():
            raise ValueError(f"Handler not found for artifact: {self.artifact_id}")
        
        # Load the module from file path
        # Append version to module name to avoid name collisions between different versions
        ver_slug = self.version.replace(".", "_").replace("-", "_")
        mod_name = f"artifact_{self.artifact_id.replace('/', '_')}_{ver_slug}_handler"
        
        spec = importlib.util.spec_from_file_location(
            mod_name,
            handler_path
        )

        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load module spec for: {handler_path}")
        
        self._module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self._module)
        
        if not hasattr(self._module, "execute"):
            raise ValueError(f"Artifact handler must define 'execute(context)' function: {self.artifact_id}")
        
        self._execute_func = self._module.execute
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        """Execute the artifact's handler."""
        try:
            self._load_module()
            
            artifact_context = ArtifactContext(
                input_data.data,
                context.config,
                input_data.metadata
            )
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._execute_func(artifact_context)
            )
            
            return OperatorOutput(
                data=result,
                metadata=input_data.metadata,
                operator_id=self.operator_id,
                success=True
            )
            
        except Exception as e:
            return OperatorOutput(
                data=None,
                operator_id=self.operator_id,
                success=False,
                error_message=f"Artifact execution error: {str(e)}\n{traceback.format_exc()}"
            )

class PassthroughExecutor(OperatorExecutor):
    """Simple passthrough operator for testing."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        return OperatorOutput(
            data=input_data.data,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class HTMLCleanerExecutor(OperatorExecutor):
    """Clean HTML content and extract text."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            # Fallback to regex-based cleaning
            import re
            
            def clean_html(html: str) -> str:
                # Remove script and style tags
                cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
                cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
                # Remove tags
                cleaned = re.sub(r'<[^>]+>', '', cleaned)
                # Normalize whitespace
                cleaned = re.sub(r'\s+', ' ', cleaned).strip()
                return cleaned
            
            documents = input_data.data
            if isinstance(documents, list):
                result = []
                for doc in documents:
                    if isinstance(doc, dict):
                        text = doc.get("text", doc.get("content", ""))
                        doc["text"] = clean_html(text)
                        result.append(doc)
                    else:
                        result.append({"text": clean_html(str(doc))})
            else:
                result = [{"text": clean_html(str(documents))}]
            
            return OperatorOutput(
                data=result,
                metadata=input_data.metadata,
                operator_id=self.operator_id,
                success=True
            )
        
        # BeautifulSoup is available
        config = context.config
        remove_scripts = config.get("remove_scripts", True)
        remove_styles = config.get("remove_styles", True)
        
        documents = input_data.data
        result = []
        
        for doc in (documents if isinstance(documents, list) else [documents]):
            if isinstance(doc, dict):
                text = doc.get("text", doc.get("content", ""))
            else:
                text = str(doc)
            
            soup = BeautifulSoup(text, "html.parser")
            
            if remove_scripts:
                for script in soup.find_all("script"):
                    script.decompose()
            
            if remove_styles:
                for style in soup.find_all("style"):
                    style.decompose()
            
            cleaned_text = soup.get_text(separator=" ", strip=True)
            
            if isinstance(doc, dict):
                doc["text"] = cleaned_text
                result.append(doc)
            else:
                result.append({"text": cleaned_text})
        
        return OperatorOutput(
            data=result,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class PIIRedactorExecutor(OperatorExecutor):
    """Detect and redact PII from documents."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        import re
        
        config = context.config
        replacement = config.get("replacement_text", "[REDACTED]")
        
        patterns = []
        if config.get("redact_emails", True):
            patterns.append(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        if config.get("redact_phones", True):
            patterns.append(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
            patterns.append(r'\b\+?1?[-.]?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b')
        if config.get("redact_ssn", True):
            patterns.append(r'\b\d{3}[-]?\d{2}[-]?\d{4}\b')
        
        combined_pattern = "|".join(f"({p})" for p in patterns) if patterns else None
        
        documents = input_data.data
        result = []
        
        for doc in (documents if isinstance(documents, list) else [documents]):
            if isinstance(doc, dict):
                text = doc.get("text", doc.get("content", ""))
            else:
                text = str(doc)
            
            if combined_pattern:
                redacted_text = re.sub(combined_pattern, replacement, text)
            else:
                redacted_text = text
            
            if isinstance(doc, dict):
                doc["text"] = redacted_text
                result.append(doc)
            else:
                result.append({"text": redacted_text})
        
        return OperatorOutput(
            data=result,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class MetadataExtractorExecutor(OperatorExecutor):
    """Extract metadata from documents."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        import re
        from datetime import datetime
        
        config = context.config
        extract_dates = config.get("extract_dates", True)
        extract_titles = config.get("extract_titles", True)
        
        # Date patterns
        date_patterns = [
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',
        ]
        
        documents = input_data.data
        result = []
        
        for doc in (documents if isinstance(documents, list) else [documents]):
            if isinstance(doc, dict):
                text = doc.get("text", doc.get("content", ""))
                metadata = doc.get("metadata", {})
            else:
                text = str(doc)
                metadata = {}
            
            extracted = {}
            
            if extract_dates:
                dates = []
                for pattern in date_patterns:
                    dates.extend(re.findall(pattern, text, re.IGNORECASE))
                if dates:
                    extracted["dates"] = dates[:5]  # Limit to 5
            
            if extract_titles:
                # Try to extract title from first line or heading
                lines = text.strip().split('\n')
                if lines:
                    first_line = lines[0].strip()
                    if len(first_line) < 200:  # Reasonable title length
                        extracted["title"] = first_line
            
            if isinstance(doc, dict):
                doc["metadata"] = {**metadata, **extracted}
                result.append(doc)
            else:
                result.append({"text": text, "metadata": extracted})
        
        return OperatorOutput(
            data=result,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class LoaderExecutor(OperatorExecutor):
    """Execute document loading."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from app.rag.factory import LoaderConfig
        
        # Merge input params with node config
        config_dict = {**context.config}
        if isinstance(input_data.data, dict) and input_data.source_operator_id is None:
            # Only merge if it's the first node and data is dict-like (input params)
            config_dict.update(input_data.data)
        source = config_dict.get("base_path") or config_dict.get("source")
        if source is None:
            raise ValueError("Missing loader source path")
            
        # Determine loader type from operator_id if not in config
        loader_type = config_dict.get("loader_type")
        if not loader_type:
            if self.operator_id == "local_loader":
                loader_type = "local"
            elif self.operator_id == "s3_loader":
                loader_type = "s3"
        
        loader_config = LoaderConfig(
            loader_type=loader_type,
            **{k: v for k, v in config_dict.items() if k != "loader_type"}
        )
        
        loader = RAGFactory.create_loader(loader_config)
        documents = await loader.load(source)
        
        # Documents usually are [Document(text=..., metadata=...)]
        # We need to return them in a serializable format if possible, 
        # but the Chunker expects Document objects or dicts.
        
        doc_list = []
        for doc in documents:
            if hasattr(doc, "model_dump"):
                doc_list.append(doc.model_dump())
            else:
                doc_list.append(doc)
                
        return OperatorOutput(
            data=doc_list,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class ChunkerExecutor(OperatorExecutor):
    """Execute text chunking."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from app.rag.factory import ChunkerConfig
        
        # Merge config
        config_dict = {**context.config}
        
        # Determine strategy from operator_id
        strategy = config_dict.get("strategy")
        if not strategy:
            if self.operator_id == "recursive_chunker":
                strategy = "recursive"
            elif self.operator_id == "token_based_chunker":
                strategy = "token_based"
        
        chunker_config = ChunkerConfig(
            strategy=strategy,
            **{k: v for k, v in config_dict.items() if k != "strategy"}
        )
        
        chunker = RAGFactory.create_chunker(chunker_config)
        
        all_chunks = []
        documents = input_data.data
        if not isinstance(documents, list):
            documents = [documents]
            
        for doc in documents:
            if isinstance(doc, dict):
                text = doc.get("text") or doc.get("content", "")
                doc_id = str(doc.get("id", "unknown"))
                metadata = doc.get("metadata", {})
            else:
                text = str(doc)
                doc_id = "unknown"
                metadata = {}
                
            chunks = chunker.chunk(text, doc_id=doc_id, metadata=metadata)
            all_chunks.extend([c.model_dump() for c in chunks])
            
        return OperatorOutput(
            data=all_chunks,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class QueryInputExecutor(OperatorExecutor):
    """Entry point for retrieval pipelines."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        # data contains the structured query from trigger params
        # Expected structure: {"text": "...", "filters": {...}, "metadata": {...}, "params": {...}}
        query_data = input_data.data or {}
        
        # If input is just a string, wrap it in a QUERY object
        if isinstance(query_data, str):
            query_data = {"text": query_data}
        
        return OperatorOutput(
            data=query_data,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class RetrievalResultExecutor(OperatorExecutor):
    """Exit point for retrieval pipelines. Captures final result."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        # This node just passes the data through, but the PipelineExecutor 
        # will recognize it as an output node based on its category.
        return OperatorOutput(
            data=input_data.data,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class EmbedderExecutor(OperatorExecutor):
    """Generate embeddings using Model Registry."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from app.services.model_resolver import ModelResolver
        from uuid import UUID
        
        model_id = context.config.get("model_id")
        if not model_id:
            raise ValueError("model_id is required for embedding generation")
            
        # Get DB from context (passed by PipelineExecutor)
        db = getattr(context, "db", None)
        tenant_id = context.tenant_id
        
        if not db:
            raise ValueError("Database session is required in execution context for model resolution")
            
        resolver = ModelResolver(db, UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id)
        embedder = await resolver.resolve_embedding(model_id)
        
        all_embeddings = []
        input_val = input_data.data
        
        # Handle DataType.QUERY
        if isinstance(input_val, dict) and "text" in input_val and "values" not in input_val:
            # It's a structured query that needs embedding
            embedding_result = await embedder.embed_batch([input_val["text"]])
            input_val["values"] = embedding_result[0].values
            return OperatorOutput(
                data=input_val, # Now it has values
                metadata=input_data.metadata,
                operator_id=self.operator_id,
                success=True
            )

        chunks = input_val if isinstance(input_val, list) else [input_val]
            
        # Extract texts for batch embedding
        texts = []
        for chunk in chunks:
            if isinstance(chunk, dict):
                texts.append(chunk.get("text", ""))
            else:
                texts.append(str(chunk))
                
        results = await embedder.embed_batch(texts)
        
        for i, chunk in enumerate(chunks):
            if isinstance(chunk, dict):
                chunk["values"] = results[i].values
                all_embeddings.append(chunk)
            else:
                all_embeddings.append({
                    "text": chunk,
                    "values": results[i].values
                })
                
        return OperatorOutput(
            data=all_embeddings,
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class StorageExecutor(OperatorExecutor):
    """Execute vector storage (legacy - for existing pipelines)."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from app.rag.factory import VectorStoreConfig
        from app.rag.interfaces.vector_store import VectorDocument
        
        config_dict = {**context.config}
        
        # Determine provider from operator_id
        provider = config_dict.get("provider")
        if not provider:
            if self.operator_id == "pinecone_store":
                provider = "pinecone"
            elif self.operator_id == "pgvector_store":
                provider = "pgvector"
            elif self.operator_id == "qdrant_store":
                provider = "qdrant"
                
        # Get index_name from config
        index_name = config_dict.get("index_name")
        if not index_name:
            raise ValueError("index_name is required for storage")
            
        vs_config = VectorStoreConfig(
            provider=provider,
            **{k: v for k, v in config_dict.items() if k not in ["provider", "index_name"]}
        )
        
        vector_store = RAGFactory.create_vector_store(vs_config)
        
        documents = input_data.data
        if not isinstance(documents, list):
            documents = [documents]
            
        vector_docs = []
        for doc in documents:
            if isinstance(doc, dict):
                # Ensure we have an ID
                doc_id = str(doc.get("id")) if doc.get("id") else str(uuid.uuid4())
                vector_docs.append(VectorDocument(
                    id=doc_id,
                    values=doc.get("values", []),
                    metadata=doc.get("metadata", {})
                ))
            else:
                # Should not happen if coming from embedder
                pass
                
        count = await vector_store.upsert(
            index_name=index_name,
            documents=vector_docs,
            namespace=config_dict.get("namespace")
        )
        
        return OperatorOutput(
            data={"upsert_count": count},
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class KnowledgeStoreSinkExecutor(OperatorExecutor):
    """
    Execute vector storage to a Knowledge Store.
    
    This executor abstracts away the underlying vector database and:
    1. Resolves the KnowledgeStore by ID
    2. Instantiates the correct VectorBackendAdapter
    3. Upserts vectors in batches
    4. Updates document/chunk counts on the store
    """
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from uuid import UUID
        from app.rag.adapters import create_adapter, VectorRecord
        from app.db.postgres.models import KnowledgeStore
        
        config_dict = {**context.config}
        
        # Get the knowledge store ID
        knowledge_store_id = config_dict.get("knowledge_store_id")
        if not knowledge_store_id:
            raise ValueError("knowledge_store_id is required for Knowledge Store sink")
        
        # Get DB from context
        db = getattr(context, "db", None)
        if not db:
            raise ValueError("Database session is required in execution context")
        
        # Fetch the knowledge store
        store = await db.get(KnowledgeStore, UUID(knowledge_store_id))
        if not store:
            raise ValueError(f"Knowledge store not found: {knowledge_store_id}")
        
        # Create the adapter based on backend
        adapter = create_adapter(store.backend, store.backend_config)
        
        # Prepare vectors
        documents = input_data.data
        if not isinstance(documents, list):
            documents = [documents]
        
        vectors = []
        for doc in documents:
            if isinstance(doc, dict):
                doc_id = str(doc.get("id")) if doc.get("id") else str(uuid.uuid4())
                vectors.append(VectorRecord(
                    id=doc_id,
                    values=doc.get("values", []),
                    text=doc.get("text", ""),
                    metadata=doc.get("metadata", {})
                ))
        
        # Upsert in batches
        batch_size = config_dict.get("batch_size", 100)
        namespace = config_dict.get("namespace", "default")
        total_upserted = 0
        
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            count = await adapter.upsert(batch, namespace)
            total_upserted += count
        
        # Update store metrics
        store.chunk_count = (store.chunk_count or 0) + total_upserted
        await db.commit()
        
        return OperatorOutput(
            data={
                "upsert_count": total_upserted,
                "knowledge_store_id": str(store.id),
                "knowledge_store_name": store.name
            },
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )



class VectorSearchExecutor(OperatorExecutor):
    """Execute semantic search."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        from app.rag.factory import VectorStoreConfig
        
        config_dict = {**context.config}
        index_name = config_dict.get("index_name")
        if not index_name:
            raise ValueError("index_name is required for search")
            
        vs_config = VectorStoreConfig(
            provider=config_dict.get("provider", "pgvector"), # default
            **{k: v for k, v in config_dict.items() if k not in ["index_name"]}
        )
        
        vector_store = RAGFactory.create_vector_store(vs_config)
        
        query_val = input_data.data
        vector = None
        filters = {}
        
        if isinstance(query_val, dict):
            vector = query_val.get("values")
            filters = query_val.get("filters", {})
        else:
            # Assume it's just the vector if it's a list
            vector = query_val
            
        if not vector:
            raise ValueError("No query vector found for search")
            
        results = await vector_store.search(
            index_name=index_name,
            query_vector=vector,
            limit=config_dict.get("top_k", 10),
            filters=filters,
            namespace=config_dict.get("namespace")
        )
        
        return OperatorOutput(
            data=[r.model_dump() for r in results],
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


class HybridSearchExecutor(OperatorExecutor):
    """Execute hybrid (vector + keyword) search."""
    
    async def execute(
        self, 
        input_data: OperatorInput, 
        context: ExecutionContext
    ) -> OperatorOutput:
        # For now, we'll use the vector store's hybrid search if supported
        # This implementation is similar to VectorSearch but passes alpha
        from app.rag.factory import VectorStoreConfig
        
        config_dict = {**context.config}
        index_name = config_dict.get("index_name")
        
        vs_config = VectorStoreConfig(
            provider=config_dict.get("provider", "pgvector"),
            **{k: v for k, v in config_dict.items() if k not in ["index_name"]}
        )
        
        vector_store = RAGFactory.create_vector_store(vs_config)
        
        query_val = input_data.data
        text = ""
        vector = None
        filters = {}
        
        if isinstance(query_val, dict):
            text = query_val.get("text", "")
            vector = query_val.get("values")
            filters = query_val.get("filters", {})
            
        if not vector or not text:
            raise ValueError("Hybrid search requires both text and query vector")
            
        results = await vector_store.search(
            index_name=index_name,
            query_vector=vector,
            query_text=text,
            limit=config_dict.get("top_k", 10),
            filters=filters,
            alpha=config_dict.get("alpha", 0.5),
            namespace=config_dict.get("namespace")
        )
        
        return OperatorOutput(
            data=[r.model_dump() for r in results],
            metadata=input_data.metadata,
            operator_id=self.operator_id,
            success=True
        )


# =============================================================================
# EXECUTOR REGISTRY
# =============================================================================

class ExecutorRegistry:
    """Registry mapping operator IDs to their executor classes."""
    
    _executors: Dict[str, type] = {
        "html_cleaner": HTMLCleanerExecutor,
        "pii_redactor": PIIRedactorExecutor,
        "metadata_extractor": MetadataExtractorExecutor,
        "local_loader": LoaderExecutor,
        "s3_loader": LoaderExecutor,
        "recursive_chunker": ChunkerExecutor,
        "token_based_chunker": ChunkerExecutor,
        "model_embedder": EmbedderExecutor,
        "knowledge_store_sink": KnowledgeStoreSinkExecutor,
        "vector_search": VectorSearchExecutor,
        "hybrid_search": HybridSearchExecutor,
        "query_input": QueryInputExecutor,
        "retrieval_result": RetrievalResultExecutor,
        "passthrough": PassthroughExecutor,
    }
    
    @classmethod
    def register(cls, operator_id: str, executor_class: type):
        """Register an executor class for an operator."""
        cls._executors[operator_id] = executor_class
    
    @classmethod
    def get(cls, operator_id: str) -> Optional[type]:
        """Get the executor class for an operator."""
        return cls._executors.get(operator_id)
    
    @classmethod
    def create_executor(
        cls, 
        spec: OperatorSpec, 
        python_code: Optional[str] = None
    ) -> OperatorExecutor:
        """Create an executor instance for an operator.
        
        Routing order:
        1. Artifacts (file-based operators from /backend/artifacts)
        2. Custom operators (DB-stored python_code)
        3. Built-in executors (hardcoded in ExecutorRegistry)
        """
        # Check if this operator is an artifact
        from app.services.artifact_registry import get_artifact_registry
        artifact_registry = get_artifact_registry()
        
        if artifact_registry.get_artifact(spec.operator_id, spec.version):
            return ArtifactExecutor(spec, spec.operator_id, spec.version)

        
        # Custom operators with inline code
        if spec.is_custom and python_code:
            return PythonOperatorExecutor(spec, python_code)
        
        # Built-in executors
        executor_class = cls.get(spec.operator_id)
        if executor_class:
            return executor_class(spec)
        
        # Raise error if no executor found (Fail-Fast)
        raise ValueError(f"No executor implementation found for operator: {spec.operator_id}")
