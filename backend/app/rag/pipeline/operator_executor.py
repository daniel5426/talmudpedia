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

from app.rag.pipeline.registry import OperatorSpec, DataType


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
# BUILT-IN OPERATOR EXECUTORS
# =============================================================================

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


# =============================================================================
# EXECUTOR REGISTRY
# =============================================================================

class ExecutorRegistry:
    """Registry mapping operator IDs to their executor classes."""
    
    _executors: Dict[str, type] = {
        "html_cleaner": HTMLCleanerExecutor,
        "pii_redactor": PIIRedactorExecutor,
        "metadata_extractor": MetadataExtractorExecutor,
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
        """Create an executor instance for an operator."""
        if spec.is_custom and python_code:
            return PythonOperatorExecutor(spec, python_code)
        
        executor_class = cls.get(spec.operator_id)
        if executor_class:
            return executor_class(spec)
        
        # Default to passthrough if no executor found
        return PassthroughExecutor(spec)
