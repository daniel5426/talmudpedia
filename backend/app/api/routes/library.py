from fastapi import APIRouter, HTTPException
import json
import os
from typing import List, Dict, Any

router = APIRouter(prefix="/library", tags=["library"])

TREE_FILE = "sefaria_tree.json"

@router.get("/menu", response_model=List[Dict[str, Any]])
async def get_library_menu():
    """
    Serve the pre-computed Sefaria library tree.
    """
    if not os.path.exists(TREE_FILE):
        # Fallback: Try to find it in the current directory or backend directory
        # This is a bit hacky but useful for dev
        if os.path.exists(os.path.join("backend", TREE_FILE)):
            tree_path = os.path.join("backend", TREE_FILE)
        else:
            raise HTTPException(status_code=503, detail="Library menu is being built. Please try again later.")
    else:
        tree_path = TREE_FILE
        
    try:
        with open(tree_path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid menu data")
