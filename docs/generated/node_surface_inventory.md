# Generated Node Surface Inventory

Last Updated: 2026-03-18

This file is generated from the live agent-node and RAG-operator registries.

## Scope
- Agent graph schema enum types.
- Registered agent node operators and executor coverage.
- Registered RAG pipeline operators and their contract surfaces.

## Summary
- Agent schema enum types: 20
- Registered agent node types: 23
- Registered RAG operators: 22

## Agent Schema Enum Types
- `cancel_subtree`
- `conditional`
- `end`
- `human_input`
- `input`
- `join`
- `judge`
- `llm`
- `llm_call`
- `loop`
- `output`
- `parallel`
- `rag_pipeline`
- `replan`
- `router`
- `spawn_group`
- `spawn_run`
- `start`
- `tool_call`
- `transform`

## Agent Registry Drift
- Schema enum types without a registered operator:
  - `input`
  - `llm_call`
  - `loop`
  - `output`
  - `rag_pipeline`
  - `tool_call`
- Registered agent node types not declared in the graph schema enum:
  - `agent`
  - `classify`
  - `if_else`
  - `rag`
  - `set_state`
  - `tool`
  - `user_approval`
  - `vector_search`
  - `while`

## Registered Agent Nodes
| Type | Category | Executor | In Schema Enum | Required Config Fields |
| --- | --- | --- | --- | --- |
| `agent` | `reasoning` | yes | no | model_id |
| `cancel_subtree` | `orchestration` | yes | yes | - |
| `classify` | `reasoning` | yes | no | - |
| `conditional` | `logic` | yes | yes | - |
| `end` | `control` | yes | yes | - |
| `human_input` | `interaction` | yes | yes | - |
| `if_else` | `logic` | yes | no | - |
| `join` | `orchestration` | yes | yes | - |
| `judge` | `orchestration` | yes | yes | - |
| `llm` | `reasoning` | yes | yes | model_id |
| `parallel` | `logic` | yes | yes | - |
| `rag` | `action` | yes | no | - |
| `replan` | `orchestration` | yes | yes | - |
| `router` | `orchestration` | yes | yes | - |
| `set_state` | `data` | yes | no | - |
| `spawn_group` | `orchestration` | yes | yes | - |
| `spawn_run` | `orchestration` | yes | yes | - |
| `start` | `control` | yes | yes | - |
| `tool` | `action` | yes | no | - |
| `transform` | `data` | yes | yes | - |
| `user_approval` | `interaction` | yes | no | - |
| `vector_search` | `action` | yes | no | - |
| `while` | `logic` | yes | no | - |

## Registered RAG Operators
| Operator | Category | Input | Output | Required Config Fields |
| --- | --- | --- | --- | --- |
| `hierarchical_chunker` | `chunking` | `enriched_documents` | `chunks` | - |
| `recursive_chunker` | `chunking` | `enriched_documents` | `chunks` | - |
| `semantic_chunker` | `chunking` | `enriched_documents` | `chunks` | model_id |
| `token_based_chunker` | `chunking` | `enriched_documents` | `chunks` | - |
| `model_embedder` | `embedding` | `chunks` | `embeddings` | model_id |
| `classifier` | `enrichment` | `normalized_documents` | `enriched_documents` | categories |
| `entity_recognizer` | `enrichment` | `normalized_documents` | `enriched_documents` | - |
| `metadata_extractor` | `enrichment` | `normalized_documents` | `enriched_documents` | - |
| `summarizer` | `enrichment` | `normalized_documents` | `enriched_documents` | model_id |
| `query_input` | `input` | `none` | `query` | text |
| `format_normalizer` | `normalization` | `raw_documents` | `normalized_documents` | - |
| `language_detector` | `normalization` | `raw_documents` | `normalized_documents` | - |
| `pii_redactor` | `normalization` | `raw_documents` | `normalized_documents` | - |
| `retrieval_result` | `output` | `search_results` | `none` | - |
| `cross_encoder_reranker` | `reranking` | `search_results` | `reranked_results` | - |
| `model_reranker` | `reranking` | `search_results` | `reranked_results` | model_id |
| `hybrid_search` | `retrieval` | `embeddings` | `search_results` | index_name |
| `vector_search` | `retrieval` | `embeddings` | `search_results` | knowledge_store_id |
| `local_loader` | `source` | `none` | `raw_documents` | base_path |
| `s3_loader` | `source` | `none` | `raw_documents` | bucket, aws_access_key_id, aws_secret_access_key |
| `web_crawler` | `source` | `none` | `raw_documents` | start_urls |
| `knowledge_store_sink` | `storage` | `embeddings` | `vectors` | knowledge_store_id |

