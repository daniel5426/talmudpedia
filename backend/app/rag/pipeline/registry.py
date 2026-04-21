"""
Operator Registry - Defines all available operators for RAG pipelines.

This module provides:
- DataType: Enum of data types flowing through the pipeline
- OperatorCategory: Enum of operator categories (source, normalization, enrichment, chunking, utility, embedding, storage, retrieval, reranking)
- ConfigFieldSpec: Configuration field specification with JSON Schema support
- OperatorSpec: Full operator specification with versioning and contracts
- OperatorRegistry: Singleton registry for all available operators
"""
from typing import Dict, List, Optional, Any, Set
from enum import Enum
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class DataType(str, Enum):
    """Data types that flow through pipeline edges."""
    ANY = "any"
    NONE = "none"
    RAW_DOCUMENTS = "raw_documents"
    NORMALIZED_DOCUMENTS = "normalized_documents"  # After normalization (OCR, HTML cleaning)
    ENRICHED_DOCUMENTS = "enriched_documents"      # After enrichment (metadata, entities)
    CHUNKS = "chunks"
    EMBEDDINGS = "embeddings"
    VECTORS = "vectors"
    SEARCH_RESULTS = "search_results"              # For query pipelines
    RERANKED_RESULTS = "reranked_results"          # After reranking
    QUERY = "query"                                # Structured query (text, filters, etc)
    QUERY_EMBEDDINGS = "query_embeddings"          # Tuple of (QUERY, vector)


class OperatorCategory(str, Enum):
    """Categories of operators in the pipeline."""
    SOURCE = "source"
    NORMALIZATION = "normalization"   # OCR, HTML cleaning, PII redaction
    ENRICHMENT = "enrichment"         # Metadata extraction, entity recognition, summarization
    CHUNKING = "chunking"             # Text chunking strategies
    UTILITY = "utility"               # Filtering, dedupe, and field-level transforms
    EMBEDDING = "embedding"           # Embedding models
    STORAGE = "storage"               # Vector stores
    RETRIEVAL = "retrieval"           # Search operators (vector, hybrid, BM25)
    RERANKING = "reranking"           # Reranker models
    INPUT = "input"                   # Pipeline entry points (e.g. Query Input)
    OUTPUT = "output"                 # Pipeline exit points (e.g. Retrieval Result)
    CUSTOM = "custom"                 # User-defined Python operators


class ConfigFieldType(str, Enum):
    """Types of configuration fields."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SECRET = "secret"
    SELECT = "select"
    MODEL_SELECT = "model_select"
    KNOWLEDGE_STORE_SELECT = "knowledge_store_select"
    RETRIEVAL_PIPELINE_SELECT = "retrieval_pipeline_select"
    JSON = "json"           # For complex nested configs
    CODE = "code"           # For Python code editors
    FILE_PATH = "file_path" # For file/directory selection


class ConfigFieldSpec(BaseModel):
    """Specification for a configuration field."""
    name: str
    field_type: ConfigFieldType
    required: bool = False
    runtime: bool = True
    default: Optional[Any] = None
    description: Optional[str] = None
    options: Optional[List[str]] = None
    required_capability: Optional[str] = None
    # JSON Schema for validation (used when field_type is JSON)
    json_schema: Optional[Dict[str, Any]] = None
    # Minimum/maximum values for numeric fields
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    # Placeholder text for UI
    placeholder: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


def data_type_contract_schema(data_type: DataType) -> Optional[Dict[str, Any]]:
    if data_type == DataType.NONE:
        return None
    if data_type == DataType.ANY:
        return {"type": ["object", "array", "string", "number", "boolean"]}
    if data_type == DataType.QUERY:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "query": {"type": "string"},
                "filters": {"type": "object"},
                "top_k": {"type": "integer"},
            },
            "additionalProperties": True,
        }
    if data_type in {
        DataType.RAW_DOCUMENTS,
        DataType.NORMALIZED_DOCUMENTS,
        DataType.ENRICHED_DOCUMENTS,
        DataType.CHUNKS,
        DataType.SEARCH_RESULTS,
        DataType.RERANKED_RESULTS,
    }:
        return {"type": "array"}
    if data_type in {DataType.EMBEDDINGS, DataType.VECTORS, DataType.QUERY_EMBEDDINGS}:
        return {"type": ["array", "object"]}
    return {"type": ["object", "array", "string", "number", "boolean"]}


class OperatorSpec(BaseModel):
    """
    Full specification of an operator.
    
    This is the "Operator Contract" - every operator must adhere to this spec.
    """
    # Identity
    operator_id: str
    display_name: str
    category: OperatorCategory
    version: str = "1.0.0"
    description: Optional[str] = None
    
    # Data flow contract
    input_type: DataType
    output_type: DataType
    
    # Input/Output JSON Schemas for strict validation
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    
    # Configuration
    required_config: List[ConfigFieldSpec] = []
    optional_config: List[ConfigFieldSpec] = []
    
    # Capabilities
    supports_parallelism: bool = False
    supports_streaming: bool = False
    supports_batching: bool = False
    max_batch_size: Optional[int] = None
    
    # Embedding-specific
    dimension: Optional[int] = None
    required_capability: Optional[str] = None
    
    # Custom operator fields
    is_custom: bool = False
    python_code: Optional[str] = None  # For custom Python operators
    artifact_id: Optional[str] = None
    artifact_revision_id: Optional[str] = None
    
    # Metadata
    author: Optional[str] = None
    tags: List[str] = []
    scope: str = "rag" # rag, agent, or both
    deprecated: bool = False
    deprecation_message: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    def get_required_field_names(self) -> Set[str]:
        return {f.name for f in self.required_config}

    def resolved_input_schema(self) -> Optional[Dict[str, Any]]:
        if isinstance(self.input_schema, dict) and self.input_schema:
            return dict(self.input_schema)
        return data_type_contract_schema(self.input_type)

    def resolved_output_schema(self) -> Optional[Dict[str, Any]]:
        if isinstance(self.output_schema, dict) and self.output_schema:
            return dict(self.output_schema)
        return data_type_contract_schema(self.output_type)

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate a configuration against this operator's spec."""
        errors = []
        required_names = {f.name for f in self.required_config if not f.runtime}
        provided_names = set(config.keys())

        missing = required_names - provided_names
        for field in missing:
            errors.append(f"Missing required config field: {field}")

        for field in self.required_config + self.optional_config:
            if field.name in config:
                value = config[field.name]
                if field.field_type == ConfigFieldType.SECRET:
                    if not isinstance(value, str) or not value.startswith("$secret:"):
                        errors.append(
                            f"Field '{field.name}' must be a secret reference (e.g., $secret:my_key)"
                        )
                elif field.field_type == ConfigFieldType.SELECT:
                    if field.options and value not in field.options:
                        errors.append(
                            f"Field '{field.name}' must be one of: {field.options}"
                        )
                elif field.field_type in {
                    ConfigFieldType.STRING,
                    ConfigFieldType.MODEL_SELECT,
                    ConfigFieldType.FILE_PATH,
                    ConfigFieldType.CODE,
                }:
                    if not isinstance(value, str):
                        errors.append(f"Field '{field.name}' must be a string")
                elif field.field_type == ConfigFieldType.INTEGER:
                    if not isinstance(value, int) or isinstance(value, bool):
                        errors.append(f"Field '{field.name}' must be an integer")
                    elif field.min_value is not None and value < field.min_value:
                        errors.append(f"Field '{field.name}' must be >= {field.min_value}")
                    elif field.max_value is not None and value > field.max_value:
                        errors.append(f"Field '{field.name}' must be <= {field.max_value}")
                elif field.field_type == ConfigFieldType.FLOAT:
                    if not isinstance(value, (int, float)) or isinstance(value, bool):
                        errors.append(f"Field '{field.name}' must be a number")
                    elif field.min_value is not None and value < field.min_value:
                        errors.append(f"Field '{field.name}' must be >= {field.min_value}")
                    elif field.max_value is not None and value > field.max_value:
                        errors.append(f"Field '{field.name}' must be <= {field.max_value}")
                elif field.field_type == ConfigFieldType.BOOLEAN:
                    if not isinstance(value, bool):
                        errors.append(f"Field '{field.name}' must be a boolean")
                elif field.field_type == ConfigFieldType.JSON:
                    if not isinstance(value, (dict, list)):
                        errors.append(f"Field '{field.name}' must be an object or list")
        return errors

    def to_catalog_entry(self) -> Dict[str, Any]:
        """Convert to catalog format for API responses."""
        return {
            "operator_id": self.operator_id,
            "display_name": self.display_name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "input_type": self.input_type.value,
            "output_type": self.output_type.value,
            "dimension": self.dimension,
            "is_custom": self.is_custom,
            "artifact_id": self.artifact_id,
            "artifact_revision_id": self.artifact_revision_id,
            "deprecated": self.deprecated,
            "tags": self.tags,
        }

    def to_agent_operator_spec(self):
        """Convert this RAG operator spec to an Agent operator spec."""
        from app.agent.registry import AgentOperatorSpec, AgentStateField
        
        # Map RAG categories to agent categories roughly
        category_map = {
            OperatorCategory.SOURCE: "action",
            OperatorCategory.NORMALIZATION: "data",
            OperatorCategory.ENRICHMENT: "action",
            OperatorCategory.CHUNKING: "data",
            OperatorCategory.UTILITY: "data",
            OperatorCategory.EMBEDDING: "action",
            OperatorCategory.STORAGE: "action",
            OperatorCategory.RETRIEVAL: "action",
            OperatorCategory.RERANKING: "action",
            OperatorCategory.INPUT: "control",
            OperatorCategory.OUTPUT: "control",
        }
        
        # Determine reads/writes based on IO types (simplified mapping)
        reads = []
        writes = []
        
        if self.input_type != DataType.NONE:
            reads.append(AgentStateField.TRANSFORM_OUTPUT) # Default input source
            
        if self.output_type != DataType.NONE:
            writes.append(AgentStateField.TRANSFORM_OUTPUT)
            
        # UI metadata
        ui = {
            "icon": "Box", # Generic icon
            "color": "#3b82f6",
            "inputType": self.input_type.value,
            "outputType": self.output_type.value,
            "configFields": []
        }
        
        # Add config fields
        for cfg in self.required_config + self.optional_config:
            ui["configFields"].append({
                "name": cfg.name,
                "label": cfg.name.replace("_", " ").title(),
                "fieldType": cfg.field_type.value,
                "required": cfg.required,
                "default": cfg.default,
                "description": cfg.description,
                "options": [{"value": o, "label": o} for o in (cfg.options or [])] if cfg.field_type == ConfigFieldType.SELECT else cfg.options
            })
            
        # Ensure ID has correct prefix for execution routing if needed
        # But here we use the full operator_id
        
        return AgentOperatorSpec(
            type=self.operator_id,
            category=category_map.get(self.category, "action"),
            display_name=self.display_name,
            description=self.description or "",
            reads=reads,
            writes=writes,
            config_schema={}, # Flexible
            ui=ui
        )


# =============================================================================
# SOURCE OPERATORS
# =============================================================================

SOURCE_OPERATORS: Dict[str, OperatorSpec] = {
    "local_loader": OperatorSpec(
        operator_id="local_loader",
        display_name="Local File Loader",
        category=OperatorCategory.SOURCE,
        version="1.0.0",
        description="Load documents from local filesystem",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="base_path",
                field_type=ConfigFieldType.FILE_PATH,
                runtime=True,
                description="Path to local directory or file",
                placeholder="/path/to/documents",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="file_extensions",
                field_type=ConfigFieldType.STRING,
                runtime=True,
                description="Comma-separated list of extensions (e.g., .txt,.md,.pdf)",
                default=".txt,.md,.pdf",
            ),
            ConfigFieldSpec(
                name="recursive",
                field_type=ConfigFieldType.BOOLEAN,
                runtime=True,
                description="Recursively scan subdirectories",
                default=True,
            ),
        ],
        tags=["filesystem", "local"],
    ),
    "s3_loader": OperatorSpec(
        operator_id="s3_loader",
        display_name="S3 Loader",
        category=OperatorCategory.SOURCE,
        version="1.0.0",
        description="Load documents from AWS S3",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="bucket",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="S3 bucket name",
            ),
            ConfigFieldSpec(
                name="aws_access_key_id",
                field_type=ConfigFieldType.SECRET,
                required=True,
                description="AWS access key ID",
            ),
            ConfigFieldSpec(
                name="aws_secret_access_key",
                field_type=ConfigFieldType.SECRET,
                required=True,
                description="AWS secret access key",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="prefix",
                field_type=ConfigFieldType.STRING,
                description="S3 key prefix",
            ),
            ConfigFieldSpec(
                name="region_name",
                field_type=ConfigFieldType.STRING,
                default="us-east-1",
                description="AWS region",
            ),
        ],
        tags=["aws", "s3", "cloud"],
    ),
    "web_crawler": OperatorSpec(
        operator_id="web_crawler",
        display_name="Web Crawler",
        category=OperatorCategory.SOURCE,
        version="1.1.0",
        description="Crawl and extract content from websites with a few high-value Crawl4AI controls",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="start_urls",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Comma-separated list of starting URLs",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="max_depth",
                field_type=ConfigFieldType.INTEGER,
                default=2,
                description="Maximum crawl depth",
                min_value=1,
                max_value=10,
            ),
            ConfigFieldSpec(
                name="max_pages",
                field_type=ConfigFieldType.INTEGER,
                default=100,
                description="Maximum pages to crawl",
                min_value=1,
                max_value=10000,
            ),
            ConfigFieldSpec(
                name="respect_robots_txt",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Respect robots.txt rules",
            ),
            ConfigFieldSpec(
                name="content_preference",
                field_type=ConfigFieldType.SELECT,
                default="fit_markdown",
                options=["fit_markdown", "raw_markdown", "html", "auto"],
                description="Preferred extracted content returned by the node",
            ),
            ConfigFieldSpec(
                name="wait_until",
                field_type=ConfigFieldType.SELECT,
                default="networkidle",
                options=["domcontentloaded", "load", "networkidle"],
                description="Browser readiness signal before extraction starts",
            ),
            ConfigFieldSpec(
                name="page_timeout_ms",
                field_type=ConfigFieldType.INTEGER,
                default=30000,
                description="Per-page timeout in milliseconds",
                min_value=1,
                max_value=300000,
            ),
            ConfigFieldSpec(
                name="scan_full_page",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Scroll long pages before extracting content",
            ),
        ],
        tags=["web", "crawler", "scraper"],
    ),
    "api_loader": OperatorSpec(
        operator_id="api_loader",
        display_name="API Loader",
        category=OperatorCategory.SOURCE,
        version="1.0.0",
        description="Load records from HTTP APIs and SaaS-style JSON endpoints",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="endpoint_url",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="HTTP endpoint to fetch data from",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="method",
                field_type=ConfigFieldType.SELECT,
                default="GET",
                options=["GET", "POST"],
                description="HTTP method",
            ),
            ConfigFieldSpec(
                name="headers",
                field_type=ConfigFieldType.JSON,
                description="Optional request headers as JSON object",
            ),
            ConfigFieldSpec(
                name="query_params",
                field_type=ConfigFieldType.JSON,
                description="Optional query parameters as JSON object",
            ),
            ConfigFieldSpec(
                name="body",
                field_type=ConfigFieldType.JSON,
                description="Optional JSON request body for POST calls",
            ),
            ConfigFieldSpec(
                name="response_path",
                field_type=ConfigFieldType.STRING,
                description="Optional dot-path to the records payload inside the response JSON",
            ),
            ConfigFieldSpec(
                name="item_text_field",
                field_type=ConfigFieldType.STRING,
                default="text",
                description="Field to treat as the document text when records are objects",
            ),
            ConfigFieldSpec(
                name="item_id_field",
                field_type=ConfigFieldType.STRING,
                default="id",
                description="Field to treat as the document identifier when records are objects",
            ),
            ConfigFieldSpec(
                name="request_timeout_ms",
                field_type=ConfigFieldType.INTEGER,
                default=30000,
                description="HTTP request timeout in milliseconds",
                min_value=1,
                max_value=300000,
            ),
        ],
        tags=["api", "http", "saas"],
    ),
}

# =============================================================================
# NORMALIZATION OPERATORS
# =============================================================================

NORMALIZATION_OPERATORS: Dict[str, OperatorSpec] = {
    "pii_redactor": OperatorSpec(
        operator_id="pii_redactor",
        display_name="PII Redactor",
        category=OperatorCategory.NORMALIZATION,
        version="1.0.0",
        description="Detect and redact personally identifiable information",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.NORMALIZED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="redact_emails",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Redact email addresses",
            ),
            ConfigFieldSpec(
                name="redact_phones",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Redact phone numbers",
            ),
            ConfigFieldSpec(
                name="redact_ssn",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Redact social security numbers",
            ),
            ConfigFieldSpec(
                name="redact_names",
                field_type=ConfigFieldType.BOOLEAN,
                default=False,
                description="Redact person names (requires NLP)",
            ),
            ConfigFieldSpec(
                name="replacement_text",
                field_type=ConfigFieldType.STRING,
                default="[REDACTED]",
                description="Text to replace PII with",
            ),
        ],
        tags=["pii", "privacy", "compliance", "gdpr"],
    ),
    "format_normalizer": OperatorSpec(
        operator_id="format_normalizer",
        display_name="Format Normalizer",
        category=OperatorCategory.NORMALIZATION,
        version="1.0.0",
        description="Normalize text formatting (whitespace, unicode, etc.)",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.NORMALIZED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="normalize_whitespace",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Normalize whitespace characters",
            ),
            ConfigFieldSpec(
                name="normalize_unicode",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Normalize unicode to NFC form",
            ),
            ConfigFieldSpec(
                name="lowercase",
                field_type=ConfigFieldType.BOOLEAN,
                default=False,
                description="Convert text to lowercase",
            ),
        ],
        tags=["formatting", "text", "unicode"],
    ),
}

# =============================================================================
# ENRICHMENT OPERATORS
# =============================================================================

ENRICHMENT_OPERATORS: Dict[str, OperatorSpec] = {
    "metadata_extractor": OperatorSpec(
        operator_id="metadata_extractor",
        display_name="Metadata Extractor",
        category=OperatorCategory.ENRICHMENT,
        version="1.0.0",
        description="Extract metadata from documents (dates, titles, authors)",
        input_type=DataType.NORMALIZED_DOCUMENTS,
        output_type=DataType.ENRICHED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="extract_dates",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Extract date mentions",
            ),
            ConfigFieldSpec(
                name="extract_titles",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Extract document titles",
            ),
            ConfigFieldSpec(
                name="extract_authors",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Extract author names",
            ),
            ConfigFieldSpec(
                name="custom_patterns",
                field_type=ConfigFieldType.JSON,
                description="Custom regex patterns for extraction",
            ),
        ],
        tags=["metadata", "extraction"],
    ),
    "entity_recognizer": OperatorSpec(
        operator_id="entity_recognizer",
        display_name="Entity Recognizer",
        category=OperatorCategory.ENRICHMENT,
        version="1.0.0",
        description="Named entity recognition (NER) for documents",
        input_type=DataType.NORMALIZED_DOCUMENTS,
        output_type=DataType.ENRICHED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="entity_types",
                field_type=ConfigFieldType.STRING,
                default="PERSON,ORG,GPE,DATE",
                description="Comma-separated entity types to extract",
            ),
            ConfigFieldSpec(
                name="model",
                field_type=ConfigFieldType.SELECT,
                default="en_core_web_sm",
                options=["en_core_web_sm", "en_core_web_md", "en_core_web_lg"],
                description="SpaCy model to use",
            ),
        ],
        supports_batching=True,
        tags=["ner", "entities", "nlp"],
    ),
    "llm": OperatorSpec(
        operator_id="llm",
        display_name="LLM Transform",
        category=OperatorCategory.ENRICHMENT,
        version="1.0.0",
        description="Apply prompt-defined LLM transforms such as summarization, rewriting, augmentation, or translation",
        input_type=DataType.NORMALIZED_DOCUMENTS,
        output_type=DataType.ENRICHED_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                required=True,
                description="LLM model for summarization",
                required_capability="completion",
            ),
            ConfigFieldSpec(
                name="prompt_template",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Prompt template. Use `{text}` to inject the current item text.",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="system_prompt",
                field_type=ConfigFieldType.STRING,
                description="Optional system prompt applied to every model call",
            ),
            ConfigFieldSpec(
                name="input_field",
                field_type=ConfigFieldType.STRING,
                default="text",
                description="Field to read from each input document",
            ),
            ConfigFieldSpec(
                name="output_field",
                field_type=ConfigFieldType.STRING,
                default="llm_output",
                description="Field to write the model result into",
            ),
            ConfigFieldSpec(
                name="mode",
                field_type=ConfigFieldType.SELECT,
                default="per_item",
                options=["per_item", "join_all"],
                description="Run once per document or once over the joined corpus",
            ),
            ConfigFieldSpec(
                name="preserve_input",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Keep original document fields when writing the model output",
            ),
        ],
        supports_parallelism=True,
        required_capability="completion",
        tags=["llm", "transform", "prompt"],
    ),
    "classifier": OperatorSpec(
        operator_id="classifier",
        display_name="Document Classifier",
        category=OperatorCategory.ENRICHMENT,
        version="1.0.0",
        description="Classify documents into categories",
        input_type=DataType.NORMALIZED_DOCUMENTS,
        output_type=DataType.ENRICHED_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="categories",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Comma-separated list of categories",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                description="LLM model for classification (uses embeddings if not set)",
                required_capability="completion",
            ),
            ConfigFieldSpec(
                name="multi_label",
                field_type=ConfigFieldType.BOOLEAN,
                default=False,
                description="Allow multiple categories per document",
            ),
        ],
        tags=["classification", "categorization"],
    ),
}

# =============================================================================
# CHUNKING OPERATORS
# =============================================================================

CHUNKING_OPERATORS: Dict[str, OperatorSpec] = {
    "chunker": OperatorSpec(
        operator_id="chunker",
        display_name="Chunker",
        category=OperatorCategory.CHUNKING,
        version="1.0.0",
        description="Chunk documents using configurable recursive, token-based, semantic, or hierarchical strategies",
        input_type=DataType.ENRICHED_DOCUMENTS,
        output_type=DataType.CHUNKS,
        optional_config=[
            ConfigFieldSpec(
                name="strategy",
                field_type=ConfigFieldType.SELECT,
                default="recursive",
                options=["recursive", "token_based", "semantic", "hierarchical"],
                description="Chunking strategy",
            ),
            ConfigFieldSpec(
                name="chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=1000,
                description="Primary chunk size for recursive or token-based chunking",
                min_value=50,
                max_value=10000,
            ),
            ConfigFieldSpec(
                name="chunk_overlap",
                field_type=ConfigFieldType.INTEGER,
                default=100,
                description="Chunk overlap for recursive or token-based chunking",
                min_value=0,
                max_value=1000,
            ),
            ConfigFieldSpec(
                name="separators",
                field_type=ConfigFieldType.STRING,
                default="\\n\\n,\\n, ",
                description="Comma-separated separators used by recursive chunking",
            ),
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                description="Embedding model used by semantic chunking",
                required_capability="embedding",
            ),
            ConfigFieldSpec(
                name="similarity_threshold",
                field_type=ConfigFieldType.FLOAT,
                default=0.8,
                description="Similarity threshold used by semantic chunking",
                min_value=0.1,
                max_value=0.99,
            ),
            ConfigFieldSpec(
                name="min_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=100,
                description="Minimum chunk size for semantic chunking",
                min_value=50,
                max_value=1000,
            ),
            ConfigFieldSpec(
                name="parent_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=2000,
                description="Parent chunk size for hierarchical chunking",
                min_value=500,
                max_value=10000,
            ),
            ConfigFieldSpec(
                name="child_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=500,
                description="Child chunk size for hierarchical chunking",
                min_value=100,
                max_value=2000,
            ),
        ],
        tags=["chunking", "strategy"],
    ),
}

# =============================================================================
# UTILITY OPERATORS
# =============================================================================

UTILITY_OPERATORS: Dict[str, OperatorSpec] = {
    "transform": OperatorSpec(
        operator_id="transform",
        display_name="Transform",
        category=OperatorCategory.UTILITY,
        version="1.0.0",
        description="Filter, deduplicate, and reshape list-like pipeline payloads between stages",
        input_type=DataType.ANY,
        output_type=DataType.ANY,
        optional_config=[
            ConfigFieldSpec(
                name="dedupe_by",
                field_type=ConfigFieldType.STRING,
                description="Optional field name used to deduplicate list items",
            ),
            ConfigFieldSpec(
                name="keep_fields",
                field_type=ConfigFieldType.STRING,
                description="Comma-separated field names to keep on object items",
            ),
            ConfigFieldSpec(
                name="drop_fields",
                field_type=ConfigFieldType.STRING,
                description="Comma-separated field names to remove from object items",
            ),
            ConfigFieldSpec(
                name="rename_fields",
                field_type=ConfigFieldType.JSON,
                description="JSON object mapping old field names to new field names",
            ),
            ConfigFieldSpec(
                name="filter_field",
                field_type=ConfigFieldType.STRING,
                description="Optional field name used for filtering object items",
            ),
            ConfigFieldSpec(
                name="filter_equals",
                field_type=ConfigFieldType.STRING,
                description="Keep items whose filter field equals this value",
            ),
            ConfigFieldSpec(
                name="filter_contains",
                field_type=ConfigFieldType.STRING,
                description="Keep items whose filter field contains this value",
            ),
        ],
        tags=["utility", "transform", "dedupe"],
    ),
}

# =============================================================================
# EMBEDDING OPERATORS
# =============================================================================

EMBEDDING_OPERATORS: Dict[str, OperatorSpec] = {
    "model_embedder": OperatorSpec(
        operator_id="model_embedder",
        display_name="Model Embedder",
        category=OperatorCategory.EMBEDDING,
        version="1.0.0",
        description="Generate embeddings using Model Registry",
        input_type=DataType.CHUNKS, # Also supports DataType.QUERY via logic
        output_type=DataType.EMBEDDINGS, # Also supports DataType.QUERY_EMBEDDINGS via logic
        input_schema={"type": ["array", "object"]},
        supports_parallelism=True,
        supports_batching=True,
        max_batch_size=100,
        dimension=None,  # Resolved dynamically
        required_capability="embedding",
        required_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                required=True,
                description="Embedding model from Model Registry",
                required_capability="embedding",
            ),
        ],
        tags=["embedding", "model-registry"],
    ),
}

# =============================================================================
# STORAGE OPERATORS
# =============================================================================

STORAGE_OPERATORS: Dict[str, OperatorSpec] = {
    "knowledge_store_sink": OperatorSpec(
        operator_id="knowledge_store_sink",
        display_name="Knowledge Store",
        category=OperatorCategory.STORAGE,
        version="1.0.0",
        description="Store embeddings in a Knowledge Store. Select a knowledge store to save your documents to.",
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.VECTORS,
        required_config=[
            ConfigFieldSpec(
                name="knowledge_store_id",
                field_type=ConfigFieldType.KNOWLEDGE_STORE_SELECT,
                required=True,
                description="Target Knowledge Store",
                placeholder="Select a Knowledge Store",
                # Options will be populated dynamically from API
                required_capability="knowledge_stores",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="namespace",
                field_type=ConfigFieldType.STRING,
                description="Optional namespace within the store",
                default="default",
            ),
            ConfigFieldSpec(
                name="batch_size",
                field_type=ConfigFieldType.INTEGER,
                description="Number of vectors to upsert per batch",
                default=100,
                min_value=1,
                max_value=1000,
            ),
        ],
        tags=["vector-store", "knowledge-store", "storage"],
    ),
}


# =============================================================================
# INPUT OPERATORS
# =============================================================================

INPUT_OPERATORS: Dict[str, OperatorSpec] = {
    "query_input": OperatorSpec(
        operator_id="query_input",
        display_name="Query Input",
        category=OperatorCategory.INPUT,
        version="1.0.0",
        description="Entry point for retrieval pipelines. Receives search text and optional filters.",
        input_type=DataType.NONE,
        output_type=DataType.QUERY,
        required_config=[
            ConfigFieldSpec(
                name="text",
                field_type=ConfigFieldType.STRING,
                required=True,
                runtime=True,
                description="Search query text",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="schema",
                field_type=ConfigFieldType.JSON,
                description="Optional JSON Schema for complex filters/metadata",
            ),
            ConfigFieldSpec(
                name="filters",
                field_type=ConfigFieldType.JSON,
                description="Optional metadata filters in JSON format",
            ),
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                runtime=True,
                description="Optional runtime result limit override",
                min_value=1,
                max_value=100,
            ),
        ],
        tags=["input", "query"],
    ),
}

# =============================================================================
# OUTPUT OPERATORS
# =============================================================================

OUTPUT_OPERATORS: Dict[str, OperatorSpec] = {
    "retrieval_result": OperatorSpec(
        operator_id="retrieval_result",
        display_name="Retrieval Result",
        category=OperatorCategory.OUTPUT,
        version="1.0.0",
        description="Exit point for retrieval pipelines. Captures final search results.",
        input_type=DataType.SEARCH_RESULTS, # Also supports DataType.RERANKED_RESULTS via logic
        output_type=DataType.NONE,
        tags=["output", "result"],
    ),
}

# =============================================================================
# RETRIEVAL OPERATORS (For Query Pipelines)
# =============================================================================

RETRIEVAL_OPERATORS: Dict[str, OperatorSpec] = {
    "vector_search": OperatorSpec(
        operator_id="vector_search",
        display_name="Vector Search",
        category=OperatorCategory.RETRIEVAL,
        version="1.0.0",
        description="Semantic search using vector similarity",
        input_type=DataType.EMBEDDINGS, # Also supports DataType.QUERY_EMBEDDINGS via logic
        output_type=DataType.SEARCH_RESULTS,
        required_config=[
            ConfigFieldSpec(
                name="knowledge_store_id",
                field_type=ConfigFieldType.KNOWLEDGE_STORE_SELECT,
                required=True,
                description="Target Knowledge Store",
                placeholder="Select a Knowledge Store",
                required_capability="knowledge_stores",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                default=10,
                description="Number of results to return",
                min_value=1,
                max_value=100,
            ),
            ConfigFieldSpec(
                name="similarity_threshold",
                field_type=ConfigFieldType.FLOAT,
                default=0.0,
                description="Minimum similarity score",
                min_value=0.0,
                max_value=1.0,
            ),
            ConfigFieldSpec(
                name="namespace",
                field_type=ConfigFieldType.STRING,
                description="Namespace to search within",
            ),
        ],
        tags=["search", "vector", "semantic"],
    ),
    "hybrid_search": OperatorSpec(
        operator_id="hybrid_search",
        display_name="Hybrid Search",
        category=OperatorCategory.RETRIEVAL,
        version="1.0.0",
        description="Combined vector and keyword search",
        input_type=DataType.EMBEDDINGS, # Also supports DataType.QUERY_EMBEDDINGS via logic
        output_type=DataType.SEARCH_RESULTS,
        required_config=[
            ConfigFieldSpec(
                name="index_name",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Vector index to search",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                default=10,
                description="Number of results to return",
                min_value=1,
                max_value=100,
            ),
            ConfigFieldSpec(
                name="alpha",
                field_type=ConfigFieldType.FLOAT,
                default=0.5,
                description="Balance between vector (1.0) and keyword (0.0)",
                min_value=0.0,
                max_value=1.0,
            ),
        ],
        tags=["search", "hybrid", "bm25", "vector"],
    ),
}

# =============================================================================
# RERANKING OPERATORS
# =============================================================================

RERANKING_OPERATORS: Dict[str, OperatorSpec] = {
    "reranker": OperatorSpec(
        operator_id="reranker",
        display_name="Reranker",
        category=OperatorCategory.RERANKING,
        version="1.0.0",
        description="Rerank retrieval results using a configurable strategy",
        input_type=DataType.SEARCH_RESULTS,
        output_type=DataType.RERANKED_RESULTS,
        optional_config=[
            ConfigFieldSpec(
                name="strategy",
                field_type=ConfigFieldType.SELECT,
                default="model",
                options=["model", "cross_encoder", "lexical"],
                description="Reranking strategy",
            ),
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                description="Optional logical reranker model identifier",
                required_capability="rerank",
            ),
            ConfigFieldSpec(
                name="model_name",
                field_type=ConfigFieldType.SELECT,
                default="cross-encoder/ms-marco-MiniLM-L-6-v2",
                options=[
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    "cross-encoder/ms-marco-MiniLM-L-12-v2",
                    "BAAI/bge-reranker-base",
                    "BAAI/bge-reranker-large",
                ],
                description="Optional named cross-encoder reranker model",
            ),
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                default=5,
                description="Number of results to keep after reranking",
                min_value=1,
                max_value=50,
            ),
        ],
        tags=["reranking", "quality", "strategy"],
    ),
}


# =============================================================================
# OPERATOR REGISTRY
# =============================================================================

class OperatorRegistry:
    """
    Singleton registry for all available operators.
    
    Provides methods to:
    - Register new operators (including custom ones)
    - Query operators by ID or category
    - Check compatibility between operators
    - Get the full catalog for UI
    """
    _instance: Optional["OperatorRegistry"] = None

    def __init__(self):
        self._operators: Dict[str, OperatorSpec] = {}
        self._custom_operators: Dict[str, OperatorSpec] = {}  # Organization-specific custom operators
        self._register_defaults()

    @classmethod
    def get_instance(cls) -> "OperatorRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton (useful for testing)."""
        cls._instance = None

    def _register_defaults(self):
        """Register all built-in operators."""
        for op in SOURCE_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in NORMALIZATION_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in ENRICHMENT_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in CHUNKING_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in UTILITY_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in EMBEDDING_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in STORAGE_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in RETRIEVAL_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in RERANKING_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in INPUT_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in OUTPUT_OPERATORS.values():
            self._operators[op.operator_id] = op
        
    def _load_artifact_operators(self):
        return None

    def register(self, spec: OperatorSpec):
        """Register a new operator."""
        self._operators[spec.operator_id] = spec

    def register_custom(self, spec: OperatorSpec, organization_id: str):
        """Register a custom operator for a specific organization."""
        key = f"{organization_id}:{spec.operator_id}"
        spec.is_custom = True
        self._custom_operators[key] = spec

    def load_custom_operators(self, specs: List[OperatorSpec], organization_id: str):
        """Batch load custom operators for a organization."""
        for spec in specs:
             self.register_custom(spec, organization_id)


    def get(self, operator_id: str, organization_id: Optional[str] = None) -> Optional[OperatorSpec]:
        """Get an operator by ID, checking custom operators first if organization_id provided."""
        if organization_id:
            custom_key = f"{organization_id}:{operator_id}"
            if custom_key in self._custom_operators:
                return self._custom_operators[custom_key]
        return self._operators.get(operator_id)

    def get_by_category(self, category: str, organization_id: Optional[str] = None) -> List[OperatorSpec]:
        """Get all operators in a category."""
        result = [op for op in self._operators.values() if op.category.value == category]
        if organization_id:
            for key, op in self._custom_operators.items():
                if key.startswith(f"{organization_id}:") and op.category.value == category:
                    result.append(op)
        return result

    def list_all(self, organization_id: Optional[str] = None) -> List[OperatorSpec]:
        """List all available operators."""
        result = list(self._operators.values())
        if organization_id:
            for key, op in self._custom_operators.items():
                if key.startswith(f"{organization_id}:"):
                    result.append(op)
        return result

    def get_catalog(self, organization_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get the full operator catalog grouped by category."""
        catalog: Dict[str, List[Dict[str, Any]]] = {
            "source": [],
            "normalization": [],
            "enrichment": [],
            "chunking": [],
            "utility": [],
            "embedding": [],
            "storage": [],
            "retrieval": [],
            "reranking": [],
            "input": [],
            "output": [],
            "custom": [],
        }
        for op in self.list_all(organization_id):
            category = op.category.value
            if category not in catalog:
                catalog[category] = []
            catalog[category].append(op.to_catalog_entry())
        return catalog

    def check_compatibility(self, source_op_id: str, target_op_id: str, organization_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Check if two operators can be connected."""
        source_spec = self.get(source_op_id, organization_id)
        target_spec = self.get(target_op_id, organization_id)

        if not source_spec:
            return False, f"Unknown operator: {source_op_id}"
        if not target_spec:
            return False, f"Unknown operator: {target_op_id}"

        # Check data type compatibility
        if source_spec.output_type == DataType.ANY or target_spec.input_type == DataType.ANY:
            return True, None
        if source_spec.output_type == target_spec.input_type:
            return True, None
        
        # Allow some flexible connections
        compatible_flows = [
            (DataType.RAW_DOCUMENTS, DataType.NORMALIZED_DOCUMENTS),
            (DataType.RAW_DOCUMENTS, DataType.ENRICHED_DOCUMENTS),  # Skip normalization
            (DataType.RAW_DOCUMENTS, DataType.CHUNKS),              # Skip all preprocessing
            (DataType.NORMALIZED_DOCUMENTS, DataType.ENRICHED_DOCUMENTS),
            (DataType.NORMALIZED_DOCUMENTS, DataType.CHUNKS),       # Skip enrichment
            (DataType.ENRICHED_DOCUMENTS, DataType.CHUNKS),
            (DataType.SEARCH_RESULTS, DataType.RERANKED_RESULTS),
            (DataType.RERANKED_RESULTS, DataType.SEARCH_RESULTS), # Reciprocal for output nodes
            (DataType.QUERY, DataType.CHUNKS),              # For embedding a query
            (DataType.QUERY, DataType.EMBEDDINGS),         # Flexible connection
            (DataType.QUERY_EMBEDDINGS, DataType.SEARCH_RESULTS), # Searching with query
            (DataType.EMBEDDINGS, DataType.SEARCH_RESULTS), # Vector search direct
            (DataType.RERANKED_RESULTS, DataType.NONE),
            (DataType.SEARCH_RESULTS, DataType.NONE),
        ]
        
        if (source_spec.output_type, target_spec.input_type) in compatible_flows:
            return True, None

        return False, (
            f"Type mismatch: {source_op_id} outputs {source_spec.output_type.value} "
            f"but {target_op_id} expects {target_spec.input_type.value}"
        )

    def get_operator_spec(self, operator_id: str, organization_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get full operator specification as dict (for API responses)."""
        spec = self.get(operator_id, organization_id)
        if not spec:
            return None
        return spec.model_dump()
