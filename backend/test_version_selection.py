import asyncio
import os
import sys
import json

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from dotenv import load_dotenv
load_dotenv("backend/.env")

from app.services.library.tree_builder import TreeBuilder

async def test_version_selection():
    """Test the version selection for a few sample books"""
    builder = TreeBuilder()
    
    # Test books
    test_titles = ["Genesis", "Berakhot", "Rashi on Genesis", "Shulchan Arukh, Orach Chayim"]
    
    print("Testing version selection for sample books:\n")
    
    for title in test_titles:
        version = await builder.get_best_hebrew_version(title)
        print(f"{title}:")
        print(f"  Best Hebrew version: {version}\n")
    
    # Now build a small part of the tree to verify it includes versions
    print("\n" + "="*60)
    print("Building a sample of the tree to verify version inclusion...")
    print("="*60 + "\n")
    
    # Get just one book from each category for testing
    indices = await builder.load_data()
    
    # Find Genesis
    genesis = next((idx for idx in indices if idx.get("title") == "Genesis"), None)
    if genesis:
        print("Building node for Genesis...")
        genesis_node = await builder.normalize_node(genesis)
        print(json.dumps({
            "title": genesis_node.get("title"),
            "heTitle": genesis_node.get("heTitle"),
            "bestHebrewVersion": genesis_node.get("bestHebrewVersion"),
            "children_count": len(genesis_node.get("children", []))
        }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_version_selection())
