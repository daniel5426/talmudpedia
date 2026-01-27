"""
Operator Registry - Defines all available operators for RAG pipelines.

This module provides:
- DataType: Enum of data types flowing through the pipeline
- OperatorCategory: Enum of operator categories (source, normalization, enrichment, chunking, embedding, storage, retrieval, reranking)
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
    NONE = "none"
    RAW_DOCUMENTS = "raw_documents"
    NORMALIZED_DOCUMENTS = "normalized_documents"  # After normalization (OCR, HTML cleaning)
    ENRICHED_DOCUMENTS = "enriched_documents"      # After enrichment (metadata, entities)
    CHUNKS = "chunks"
    EMBEDDINGS = "embeddings"
    VECTORS = "vectors"
    SEARCH_RESULTS = "search_results"              # For query pipelines
    RERANKED_RESULTS = "reranked_results"          # After reranking


class OperatorCategory(str, Enum):
    """Categories of operators in the pipeline."""
    SOURCE = "source"
    NORMALIZATION = "normalization"   # OCR, HTML cleaning, PII redaction
    ENRICHMENT = "enrichment"         # Metadata extraction, entity recognition, summarization
    CHUNKING = "chunking"             # Text chunking strategies
    EMBEDDING = "embedding"           # Embedding models
    STORAGE = "storage"               # Vector stores
    RETRIEVAL = "retrieval"           # Search operators (vector, hybrid, BM25)
    RERANKING = "reranking"           # Reranker models
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
    JSON = "json"           # For complex nested configs
    CODE = "code"           # For Python code editors
    FILE_PATH = "file_path" # For file/directory selection


class ConfigFieldSpec(BaseModel):
    """Specification for a configuration field."""
    name: str
    field_type: ConfigFieldType
    required: bool = False
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
    
    # Metadata
    author: Optional[str] = None
    tags: List[str] = []
    deprecated: bool = False
    deprecation_message: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    def get_required_field_names(self) -> Set[str]:
        return {f.name for f in self.required_config}

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate a configuration against this operator's spec."""
        errors = []
        required_names = self.get_required_field_names()
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
                elif field.field_type == ConfigFieldType.INTEGER:
                    if not isinstance(value, int):
                        errors.append(f"Field '{field.name}' must be an integer")
                    elif field.min_value is not None and value < field.min_value:
                        errors.append(f"Field '{field.name}' must be >= {field.min_value}")
                    elif field.max_value is not None and value > field.max_value:
                        errors.append(f"Field '{field.name}' must be <= {field.max_value}")
                elif field.field_type == ConfigFieldType.FLOAT:
                    if not isinstance(value, (int, float)):
                        errors.append(f"Field '{field.name}' must be a number")
                    elif field.min_value is not None and value < field.min_value:
                        errors.append(f"Field '{field.name}' must be >= {field.min_value}")
                    elif field.max_value is not None and value > field.max_value:
                        errors.append(f"Field '{field.name}' must be <= {field.max_value}")
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
            "deprecated": self.deprecated,
            "tags": self.tags,
        }


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
                required=True,
                description="Path to local directory or file",
                placeholder="/path/to/documents",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="file_extensions",
                field_type=ConfigFieldType.STRING,
                description="Comma-separated list of extensions (e.g., .txt,.md,.pdf)",
                default=".txt,.md,.pdf",
            ),
            ConfigFieldSpec(
                name="recursive",
                field_type=ConfigFieldType.BOOLEAN,
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
        version="1.0.0",
        description="Crawl and extract content from websites",
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
        ],
        tags=["web", "crawler", "scraper"],
    ),
}

# =============================================================================
# NORMALIZATION OPERATORS
# =============================================================================

NORMALIZATION_OPERATORS: Dict[str, OperatorSpec] = {
    "html_cleaner": OperatorSpec(
        operator_id="html_cleaner",
        display_name="HTML Cleaner",
        category=OperatorCategory.NORMALIZATION,
        version="1.0.0",
        description="Clean HTML content and extract plain text",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.NORMALIZED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="remove_scripts",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Remove script tags",
            ),
            ConfigFieldSpec(
                name="remove_styles",
                field_type=ConfigFieldType.BOOLEAN,
                default=True,
                description="Remove style tags",
            ),
            ConfigFieldSpec(
                name="preserve_links",
                field_type=ConfigFieldType.BOOLEAN,
                default=False,
                description="Preserve link URLs in output",
            ),
        ],
        tags=["html", "cleaning", "text"],
    ),
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
    "language_detector": OperatorSpec(
        operator_id="language_detector",
        display_name="Language Detector",
        category=OperatorCategory.NORMALIZATION,
        version="1.0.0",
        description="Detect document language and add to metadata",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.NORMALIZED_DOCUMENTS,
        optional_config=[
            ConfigFieldSpec(
                name="filter_languages",
                field_type=ConfigFieldType.STRING,
                description="Comma-separated list of languages to keep (e.g., en,es,fr)",
            ),
        ],
        tags=["language", "detection", "i18n"],
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
    "summarizer": OperatorSpec(
        operator_id="summarizer",
        display_name="Document Summarizer",
        category=OperatorCategory.ENRICHMENT,
        version="1.0.0",
        description="Generate summaries of documents",
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
        ],
        optional_config=[
            ConfigFieldSpec(
                name="max_summary_length",
                field_type=ConfigFieldType.INTEGER,
                default=200,
                description="Maximum summary length in tokens",
                min_value=50,
                max_value=1000,
            ),
            ConfigFieldSpec(
                name="summary_style",
                field_type=ConfigFieldType.SELECT,
                default="concise",
                options=["concise", "detailed", "bullet_points"],
                description="Style of summary",
            ),
        ],
        supports_parallelism=True,
        required_capability="completion",
        tags=["summarization", "llm", "nlp"],
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
    "token_based_chunker": OperatorSpec(
        operator_id="token_based_chunker",
        display_name="Token-Based Chunker",
        category=OperatorCategory.CHUNKING,
        version="1.0.0",
        description="Split documents by token count",
        input_type=DataType.ENRICHED_DOCUMENTS,
        output_type=DataType.CHUNKS,
        optional_config=[
            ConfigFieldSpec(
                name="chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=650,
                description="Target token count per chunk",
                min_value=50,
                max_value=8000,
            ),
            ConfigFieldSpec(
                name="chunk_overlap",
                field_type=ConfigFieldType.INTEGER,
                default=50,
                description="Overlap tokens between chunks",
                min_value=0,
                max_value=500,
            ),
        ],
        tags=["chunking", "token"],
    ),
    "recursive_chunker": OperatorSpec(
        operator_id="recursive_chunker",
        display_name="Recursive Character Chunker",
        category=OperatorCategory.CHUNKING,
        version="1.0.0",
        description="Recursively split by characters with separators",
        input_type=DataType.ENRICHED_DOCUMENTS,
        output_type=DataType.CHUNKS,
        optional_config=[
            ConfigFieldSpec(
                name="chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=1000,
                description="Max characters per chunk",
                min_value=100,
                max_value=10000,
            ),
            ConfigFieldSpec(
                name="chunk_overlap",
                field_type=ConfigFieldType.INTEGER,
                default=200,
                description="Overlap characters between chunks",
                min_value=0,
                max_value=1000,
            ),
            ConfigFieldSpec(
                name="separators",
                field_type=ConfigFieldType.STRING,
                default="\\n\\n,\\n, ",
                description="Comma-separated list of split separators",
            ),
        ],
        tags=["chunking", "recursive", "character"],
    ),
    "semantic_chunker": OperatorSpec(
        operator_id="semantic_chunker",
        display_name="Semantic Chunker",
        category=OperatorCategory.CHUNKING,
        version="1.0.0",
        description="Split documents based on semantic similarity",
        input_type=DataType.ENRICHED_DOCUMENTS,
        output_type=DataType.CHUNKS,
        required_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                required=True,
                description="Embedding model for semantic similarity",
                required_capability="embedding",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="similarity_threshold",
                field_type=ConfigFieldType.FLOAT,
                default=0.8,
                description="Threshold for semantic similarity",
                min_value=0.1,
                max_value=0.99,
            ),
            ConfigFieldSpec(
                name="min_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=100,
                description="Minimum chunk size in characters",
                min_value=50,
                max_value=1000,
            ),
        ],
        required_capability="embedding",
        tags=["chunking", "semantic", "embeddings"],
    ),
    "hierarchical_chunker": OperatorSpec(
        operator_id="hierarchical_chunker",
        display_name="Hierarchical Chunker",
        category=OperatorCategory.CHUNKING,
        version="1.0.0",
        description="Create hierarchical chunks (parent-child relationships)",
        input_type=DataType.ENRICHED_DOCUMENTS,
        output_type=DataType.CHUNKS,
        optional_config=[
            ConfigFieldSpec(
                name="parent_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=2000,
                description="Size of parent chunks",
                min_value=500,
                max_value=10000,
            ),
            ConfigFieldSpec(
                name="child_chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=500,
                description="Size of child chunks",
                min_value=100,
                max_value=2000,
            ),
        ],
        tags=["chunking", "hierarchical", "parent-child"],
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
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS,
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
    "pinecone_store": OperatorSpec(
        operator_id="pinecone_store",
        display_name="Pinecone Vector Store",
        category=OperatorCategory.STORAGE,
        version="1.0.0",
        description="Store vectors in Pinecone",
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.VECTORS,
        required_config=[
            ConfigFieldSpec(
                name="index_name",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Target Pinecone index name",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="api_key",
                field_type=ConfigFieldType.SECRET,
                description="Pinecone API key (uses env if not set)",
            ),
            ConfigFieldSpec(
                name="namespace",
                field_type=ConfigFieldType.STRING,
                description="Pinecone namespace",
            ),
        ],
        tags=["vector-store", "pinecone", "cloud"],
    ),
    "pgvector_store": OperatorSpec(
        operator_id="pgvector_store",
        display_name="PGVector Store",
        category=OperatorCategory.STORAGE,
        version="1.0.0",
        description="Store vectors in PostgreSQL with pgvector",
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.VECTORS,
        required_config=[
            ConfigFieldSpec(
                name="table_name",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Target table name",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="connection_string",
                field_type=ConfigFieldType.SECRET,
                description="PostgreSQL connection string (uses default if not set)",
            ),
        ],
        tags=["vector-store", "postgres", "pgvector"],
    ),
    "qdrant_store": OperatorSpec(
        operator_id="qdrant_store",
        display_name="Qdrant Vector Store",
        category=OperatorCategory.STORAGE,
        version="1.0.0",
        description="Store vectors in Qdrant",
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.VECTORS,
        required_config=[
            ConfigFieldSpec(
                name="url",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Qdrant server URL",
            ),
            ConfigFieldSpec(
                name="collection_name",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Qdrant collection name",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="api_key",
                field_type=ConfigFieldType.SECRET,
                description="Qdrant API key",
            ),
        ],
        tags=["vector-store", "qdrant"],
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
        input_type=DataType.EMBEDDINGS,
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
        input_type=DataType.EMBEDDINGS,
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
    "model_reranker": OperatorSpec(
        operator_id="model_reranker",
        display_name="Model Reranker",
        category=OperatorCategory.RERANKING,
        version="1.0.0",
        description="Rerank search results using a reranker model",
        input_type=DataType.SEARCH_RESULTS,
        output_type=DataType.RERANKED_RESULTS,
        required_config=[
            ConfigFieldSpec(
                name="model_id",
                field_type=ConfigFieldType.MODEL_SELECT,
                required=True,
                description="Reranker model from Model Registry",
                required_capability="rerank",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                default=5,
                description="Number of results to keep after reranking",
                min_value=1,
                max_value=50,
            ),
        ],
        required_capability="rerank",
        tags=["reranking", "quality"],
    ),
    "cross_encoder_reranker": OperatorSpec(
        operator_id="cross_encoder_reranker",
        display_name="Cross-Encoder Reranker",
        category=OperatorCategory.RERANKING,
        version="1.0.0",
        description="Rerank using local cross-encoder model",
        input_type=DataType.SEARCH_RESULTS,
        output_type=DataType.RERANKED_RESULTS,
        optional_config=[
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
                description="HuggingFace cross-encoder model",
            ),
            ConfigFieldSpec(
                name="top_k",
                field_type=ConfigFieldType.INTEGER,
                default=5,
                description="Number of results to keep",
                min_value=1,
                max_value=50,
            ),
        ],
        tags=["reranking", "cross-encoder", "local"],
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
        self._custom_operators: Dict[str, OperatorSpec] = {}  # Tenant-specific custom operators
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
        for op in EMBEDDING_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in STORAGE_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in RETRIEVAL_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in RERANKING_OPERATORS.values():
            self._operators[op.operator_id] = op

    def register(self, spec: OperatorSpec):
        """Register a new operator."""
        self._operators[spec.operator_id] = spec

    def register_custom(self, spec: OperatorSpec, tenant_id: str):
        """Register a custom operator for a specific tenant."""
        key = f"{tenant_id}:{spec.operator_id}"
        spec.is_custom = True
        self._custom_operators[key] = spec

    def load_custom_operators(self, specs: List[OperatorSpec], tenant_id: str):
        """Batch load custom operators for a tenant."""
        for spec in specs:
             self.register_custom(spec, tenant_id)


    def get(self, operator_id: str, tenant_id: Optional[str] = None) -> Optional[OperatorSpec]:
        """Get an operator by ID, checking custom operators first if tenant_id provided."""
        if tenant_id:
            custom_key = f"{tenant_id}:{operator_id}"
            if custom_key in self._custom_operators:
                return self._custom_operators[custom_key]
        return self._operators.get(operator_id)

    def get_by_category(self, category: str, tenant_id: Optional[str] = None) -> List[OperatorSpec]:
        """Get all operators in a category."""
        result = [op for op in self._operators.values() if op.category.value == category]
        if tenant_id:
            for key, op in self._custom_operators.items():
                if key.startswith(f"{tenant_id}:") and op.category.value == category:
                    result.append(op)
        return result

    def list_all(self, tenant_id: Optional[str] = None) -> List[OperatorSpec]:
        """List all available operators."""
        result = list(self._operators.values())
        if tenant_id:
            for key, op in self._custom_operators.items():
                if key.startswith(f"{tenant_id}:"):
                    result.append(op)
        return result

    def get_catalog(self, tenant_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Get the full operator catalog grouped by category."""
        catalog: Dict[str, List[Dict[str, Any]]] = {
            "source": [],
            "normalization": [],
            "enrichment": [],
            "chunking": [],
            "embedding": [],
            "storage": [],
            "retrieval": [],
            "reranking": [],
            "custom": [],
        }
        for op in self.list_all(tenant_id):
            category = op.category.value
            if category not in catalog:
                catalog[category] = []
            catalog[category].append(op.to_catalog_entry())
        return catalog

    def check_compatibility(self, source_op_id: str, target_op_id: str, tenant_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
        """Check if two operators can be connected."""
        source_spec = self.get(source_op_id, tenant_id)
        target_spec = self.get(target_op_id, tenant_id)

        if not source_spec:
            return False, f"Unknown operator: {source_op_id}"
        if not target_spec:
            return False, f"Unknown operator: {target_op_id}"

        # Check data type compatibility
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
        ]
        
        if (source_spec.output_type, target_spec.input_type) in compatible_flows:
            return True, None

        return False, (
            f"Type mismatch: {source_op_id} outputs {source_spec.output_type.value} "
            f"but {target_op_id} expects {target_spec.input_type.value}"
        )

    def get_operator_spec(self, operator_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get full operator specification as dict (for API responses)."""
        spec = self.get(operator_id, tenant_id)
        if not spec:
            return None
        return spec.model_dump()
