DO $$
DECLARE
    v_python_code TEXT := $CODE$
def execute(context):
    """
    Sefaria Source Operator
    
    Args:
        context: Contains config (index_title, limit, version)
    
    Returns:
        List of raw document objects.
    """
    config = context.config
    index_title = config.get("index_title", "Shulchan Arukh, Orach Chayim")
    limit = config.get("limit", 10)
    version = config.get("version", "primary")
    
    BASE_URL = "https://www.sefaria.org/api"
    
    def fetch_text(ref, v):
        url = f"{BASE_URL}/v3/texts/{ref}"
        res = requests.get(url, params={"version": v}, timeout=30)
        res.raise_for_status()
        return res.json()

    # Simple implementation for testing
    print(f"Fetching {index_title} from Sefaria...")
    
    # We'll just fetch the first few segments to keep it fast
    # Real implementation would follow 'next' links
    current_ref = f"{index_title} 1:1"
    all_segments = []
    count = 0
    
    while count < limit and current_ref:
        data = fetch_text(current_ref, version)
        if not data or not data.get('versions'):
            break
            
        texts = data['versions'][0].get('text', [])
        if isinstance(texts, str):
            texts = [texts]
            
        section_ref = data.get("ref")
        
        for i, segment_text in enumerate(texts):
            if count >= limit:
                break
            
            segment_ref = f"{section_ref}:{i+1}" if len(texts) > 1 else section_ref
            
            all_segments.append({
                "id": segment_ref,
                "text": segment_text,
                "metadata": {
                    "ref": segment_ref,
                    "index_title": index_title,
                    "source": "sefaria"
                }
            })
            count += 1
            
        current_ref = data.get("next")
        
    return all_segments
$CODE$;
        v_config_schema JSONB := '[
        {
            "name": "index_title",
            "field_type": "string",
            "required": true,
            "description": "The title of the Sefaria book to ingest",
            "placeholder": "Mishnah Berakhot"
        },
        {
            "name": "limit",
            "field_type": "integer",
            "required": false,
            "default": 10,
            "description": "Maximum number of segments to fetch",
            "min_value": 1,
            "max_value": 1000
        },
        {
            "name": "version",
            "field_type": "string",
            "required": false,
            "default": "primary",
            "description": "Which version of the text to fetch"
        }
    ]'::jsonb;
    v_tenant_id UUID := 'd503d6dd-2b78-4768-95ab-4c6c84a2f194';
BEGIN
    IF EXISTS (SELECT 1 FROM custom_operators WHERE tenant_id = v_tenant_id AND name = 'sefaria_source') THEN
        UPDATE custom_operators 
        SET python_code = v_python_code, 
            config_schema = v_config_schema,
            display_name = 'Sefaria Source',
            updated_at = NOW()
        WHERE tenant_id = v_tenant_id AND name = 'sefaria_source';
        RAISE NOTICE 'Updated existing sefaria_source operator';
    ELSE
        INSERT INTO custom_operators 
        (id, tenant_id, name, display_name, category, description, python_code, input_type, output_type, config_schema, version, is_active, created_at, updated_at) 
        VALUES 
        (gen_random_uuid(), v_tenant_id, 'sefaria_source', 'Sefaria Source', 'SOURCE', 'Custom operator to fetch texts from Sefaria API', v_python_code, 'none', 'raw_documents', v_config_schema, '1.0.0', true, NOW(), NOW());
        RAISE NOTICE 'Created new sefaria_source operator';
    END IF;
END $$;
