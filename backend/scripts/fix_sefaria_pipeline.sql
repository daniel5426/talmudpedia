DO $$
DECLARE
    v_tenant_id UUID := 'd503d6dd-2b78-4768-95ab-4c6c84a2f194';
    v_nodes JSONB := '[
        {
            "id": "node-sefaria", 
            "config": {"index_title": "Mishnah Berakhot", "limit": 10, "version": "primary"}, 
            "category": "source", 
            "operator": "sefaria_source", 
            "position": {"x": 100, "y": 100},
            "display_name": "Sefaria Source"
        },
        {
            "id": "node-chunker", 
            "config": {"chunk_size": 1000, "chunk_overlap": 100}, 
            "category": "chunking", 
            "operator": "recursive_chunker", 
            "position": {"x": 100, "y": 250},
            "display_name": "Recursive Chunker"
        },
        {
            "id": "node-embedder", 
            "config": {"model_id": "gemini-embedding-001"}, 
            "category": "embedding", 
            "operator": "model_embedder", 
            "position": {"x": 100, "y": 400},
            "display_name": "Model Embedder"
        },
        {
            "id": "node-pinecone", 
            "config": {"index_name": "talmudpedia"}, 
            "category": "storage", 
            "operator": "pinecone_store", 
            "position": {"x": 100, "y": 550},
            "display_name": "Pinecone Store"
        }
    ]'::jsonb;
BEGIN
    -- Update the existing pipeline
    UPDATE visual_pipelines 
    SET nodes = v_nodes
    WHERE tenant_id = v_tenant_id AND name = 'Sefaria Ingestion Pipeline';
    
    RAISE NOTICE 'Updated Visual Pipeline: Sefaria Ingestion Pipeline with lowercase categories';
END $$;
