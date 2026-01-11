from typing import Dict, List, Optional, Any, Set
from enum import Enum
from pydantic import BaseModel, ConfigDict


class DataType(str, Enum):
    NONE = "none"
    RAW_DOCUMENTS = "raw_documents"
    CHUNKS = "chunks"
    EMBEDDINGS = "embeddings"
    VECTORS = "vectors"


class ConfigFieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    SECRET = "secret"
    SELECT = "select"


class ConfigFieldSpec(BaseModel):
    name: str
    field_type: ConfigFieldType
    required: bool = False
    default: Optional[Any] = None
    description: Optional[str] = None
    options: Optional[List[str]] = None

    model_config = ConfigDict(extra="forbid")


class OperatorSpec(BaseModel):
    operator_id: str
    display_name: str
    category: str
    input_type: DataType
    output_type: DataType
    required_config: List[ConfigFieldSpec] = []
    optional_config: List[ConfigFieldSpec] = []
    supports_parallelism: bool = False
    supports_streaming: bool = False
    dimension: Optional[int] = None

    model_config = ConfigDict(extra="forbid")

    def get_required_field_names(self) -> Set[str]:
        return {f.name for f in self.required_config}

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
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
        return errors


SOURCE_OPERATORS: Dict[str, OperatorSpec] = {
    "local_loader": OperatorSpec(
        operator_id="local_loader",
        display_name="Local File Loader",
        category="source",
        input_type=DataType.NONE,
        output_type=DataType.RAW_DOCUMENTS,
        required_config=[
            ConfigFieldSpec(
                name="base_path",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Path to local directory or file",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="file_extensions",
                field_type=ConfigFieldType.STRING,
                description="Comma-separated list of extensions (e.g., .txt,.md)",
            ),
        ],
    ),
    "s3_loader": OperatorSpec(
        operator_id="s3_loader",
        display_name="S3 Loader",
        category="source",
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
    ),
}


TRANSFORM_OPERATORS: Dict[str, OperatorSpec] = {
    "token_based_chunker": OperatorSpec(
        operator_id="token_based_chunker",
        display_name="Token-Based Chunker",
        category="transform",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.CHUNKS,
        required_config=[],
        optional_config=[
            ConfigFieldSpec(
                name="chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=650,
                description="Target token count per chunk",
            ),
            ConfigFieldSpec(
                name="chunk_overlap",
                field_type=ConfigFieldType.INTEGER,
                default=50,
                description="Overlap tokens between chunks",
            ),
        ],
    ),
    "recursive_chunker": OperatorSpec(
        operator_id="recursive_chunker",
        display_name="Recursive Chunker",
        category="transform",
        input_type=DataType.RAW_DOCUMENTS,
        output_type=DataType.CHUNKS,
        required_config=[],
        optional_config=[
            ConfigFieldSpec(
                name="chunk_size",
                field_type=ConfigFieldType.INTEGER,
                default=1000,
                description="Max characters per chunk",
            ),
            ConfigFieldSpec(
                name="chunk_overlap",
                field_type=ConfigFieldType.INTEGER,
                default=200,
                description="Overlap characters between chunks",
            ),
        ],
    ),
}


EMBEDDING_OPERATORS: Dict[str, OperatorSpec] = {
    "gemini_embedder": OperatorSpec(
        operator_id="gemini_embedder",
        display_name="Gemini Embedder",
        category="embedding",
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS,
        dimension=768,
        supports_parallelism=True,
        required_config=[],
        optional_config=[
            ConfigFieldSpec(
                name="api_key",
                field_type=ConfigFieldType.SECRET,
                description="Gemini API key (uses env if not set)",
            ),
            ConfigFieldSpec(
                name="model",
                field_type=ConfigFieldType.SELECT,
                default="gemini-embedding-001",
                options=["gemini-embedding-001"],
                description="Gemini embedding model",
            ),
        ],
    ),
    "openai_embedder": OperatorSpec(
        operator_id="openai_embedder",
        display_name="OpenAI Embedder",
        category="embedding",
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS,
        dimension=1536,
        supports_parallelism=True,
        required_config=[
            ConfigFieldSpec(
                name="api_key",
                field_type=ConfigFieldType.SECRET,
                required=True,
                description="OpenAI API key",
            ),
        ],
        optional_config=[
            ConfigFieldSpec(
                name="model",
                field_type=ConfigFieldType.SELECT,
                default="text-embedding-3-small",
                options=["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
                description="OpenAI embedding model",
            ),
        ],
    ),
    "huggingface_embedder": OperatorSpec(
        operator_id="huggingface_embedder",
        display_name="HuggingFace Embedder",
        category="embedding",
        input_type=DataType.CHUNKS,
        output_type=DataType.EMBEDDINGS,
        dimension=384,
        required_config=[],
        optional_config=[
            ConfigFieldSpec(
                name="model",
                field_type=ConfigFieldType.STRING,
                default="sentence-transformers/all-MiniLM-L6-v2",
                description="HuggingFace model name",
            ),
        ],
    ),
}


STORAGE_OPERATORS: Dict[str, OperatorSpec] = {
    "pinecone_store": OperatorSpec(
        operator_id="pinecone_store",
        display_name="Pinecone Vector Store",
        category="storage",
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
    ),
    "pgvector_store": OperatorSpec(
        operator_id="pgvector_store",
        display_name="PGVector Store",
        category="storage",
        input_type=DataType.EMBEDDINGS,
        output_type=DataType.VECTORS,
        required_config=[
            ConfigFieldSpec(
                name="connection_string",
                field_type=ConfigFieldType.SECRET,
                required=True,
                description="PostgreSQL connection string",
            ),
            ConfigFieldSpec(
                name="table_name",
                field_type=ConfigFieldType.STRING,
                required=True,
                description="Target table name",
            ),
        ],
    ),
    "qdrant_store": OperatorSpec(
        operator_id="qdrant_store",
        display_name="Qdrant Vector Store",
        category="storage",
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
    ),
}


class OperatorRegistry:
    _instance: Optional["OperatorRegistry"] = None

    def __init__(self):
        self._operators: Dict[str, OperatorSpec] = {}
        self._register_defaults()

    @classmethod
    def get_instance(cls) -> "OperatorRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _register_defaults(self):
        for op in SOURCE_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in TRANSFORM_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in EMBEDDING_OPERATORS.values():
            self._operators[op.operator_id] = op
        for op in STORAGE_OPERATORS.values():
            self._operators[op.operator_id] = op

    def register(self, spec: OperatorSpec):
        self._operators[spec.operator_id] = spec

    def get(self, operator_id: str) -> Optional[OperatorSpec]:
        return self._operators.get(operator_id)

    def get_by_category(self, category: str) -> List[OperatorSpec]:
        return [op for op in self._operators.values() if op.category == category]

    def list_all(self) -> List[OperatorSpec]:
        return list(self._operators.values())

    def get_catalog(self) -> Dict[str, List[Dict[str, Any]]]:
        catalog: Dict[str, List[Dict[str, Any]]] = {
            "source": [],
            "transform": [],
            "embedding": [],
            "storage": [],
        }
        for op in self._operators.values():
            catalog[op.category].append({
                "operator_id": op.operator_id,
                "display_name": op.display_name,
                "input_type": op.input_type.value,
                "output_type": op.output_type.value,
                "dimension": op.dimension,
            })
        return catalog

    def check_compatibility(self, source_op_id: str, target_op_id: str) -> tuple[bool, Optional[str]]:
        source_spec = self.get(source_op_id)
        target_spec = self.get(target_op_id)

        if not source_spec:
            return False, f"Unknown operator: {source_op_id}"
        if not target_spec:
            return False, f"Unknown operator: {target_op_id}"

        if source_spec.output_type != target_spec.input_type:
            return False, (
                f"Type mismatch: {source_op_id} outputs {source_spec.output_type.value} "
                f"but {target_op_id} expects {target_spec.input_type.value}"
            )

        return True, None
