DO $$
DECLARE
    v_tenant_id UUID := 'd503d6dd-2b78-4768-95ab-4c6c84a2f194';
    v_pipeline_id UUID := gen_random_uuid();
    v_nodes JSONB := '[
        {
            "id": "node-sefaria", 
            "config": {"index_title": "Mishnah Berakhot", "limit": 10, "version": "primary"}, 
            "category": "SOURCE", 
            "operator": "sefaria_source", 
            "position": {"x": 100, "y": 100},
            "display_name": "Sefaria Source"
        },
        {
            "id": "node-chunker", 
            "config": {"chunk_size": 1000, "chunk_overlap": 100}, 
            "category": "CHUNKING", 
            "operator": "recursive_chunker", 
            "position": {"x": 100, "y": 250},
            "display_name": "Recursive Chunker"
        },
        {
            "id": "node-embedder", 
            "config": {"model_id": "gemini-embedding-001"}, 
            "category": "EMBEDDING", 
            "operator": "model_embedder", 
            "position": {"x": 100, "y": 400},
            "display_name": "Model Embedder"
        },
        {
            "id": "node-pinecone", 
            "config": {"index_name": "talmudpedia"}, 
            "category": "STORAGE", 
            "operator": "pinecone_store", 
            "position": {"x": 100, "y": 550},
            "display_name": "Pinecone Store"
        }
    ]'::jsonb;
    v_edges JSONB := '[
        {
            "id": "e-1", 
            "source": "node-sefaria", 
            "target": "node-chunker", 
            "source_handle": null, 
            "target_handle": null
        },
        {
            "id": "e-2", 
            "source": "node-chunker", 
            "target": "node-embedder", 
            "source_handle": null, 
            "target_handle": null
        },
        {
            "id": "e-3", 
            "source": "node-embedder", 
            "target": "node-pinecone", 
            "source_handle": null, 
            "target_handle": null
        }
    ]'::jsonb;
BEGIN
    INSERT INTO visual_pipelines (id, tenant_id, name, description, nodes, edges, version, is_published, created_at, updated_at)
    VALUES (v_pipeline_id, v_tenant_id, 'Sefaria Ingestion Pipeline', 'Pre-configured pipeline for Sefaria text ingestion recreation', v_nodes, v_edges, 1, false, NOW(), NOW());
    
    RAISE NOTICE 'Created Visual Pipeline: Sefaria Ingestion Pipeline (ID: %)', v_pipeline_id;
END $$;
