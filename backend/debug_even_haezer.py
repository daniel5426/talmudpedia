import asyncio
import aiohttp
import json

async def debug_even_haezer():
    """Debug script to understand the Even HaEzer schema structure."""
    
    url = "https://www.sefaria.org/api/v2/index/Shulchan_Arukh,_Even_HaEzer"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                
                print("="*80)
                print("FULL RESPONSE")
                print("="*80)
                print(json.dumps(data, indent=2, ensure_ascii=False))
                
                print("\n" + "="*80)
                print("SCHEMA ANALYSIS")
                print("="*80)
                
                schema = data.get("schema", {})
                print(f"\nSchema nodeType: {schema.get('nodeType')}")
                print(f"Schema has 'nodes': {'nodes' in schema}")
                
                if "nodes" in schema:
                    nodes = schema["nodes"]
                    print(f"\nNumber of nodes: {len(nodes)}")
                    
                    for i, node in enumerate(nodes):
                        print(f"\n--- Node {i} ---")
                        print(f"  nodeType: {node.get('nodeType')}")
                        print(f"  title: '{node.get('title', '')}'")
                        print(f"  heTitle: '{node.get('heTitle', '')}'")
                        print(f"  key: '{node.get('key', '')}'")
                        print(f"  default: {node.get('default', False)}")
                        print(f"  depth: {node.get('depth')}")
                        print(f"  sectionNames: {node.get('sectionNames', [])}")
                        print(f"  heSectionNames: {node.get('heSectionNames', [])}")
                        
                        if "content_counts" in node:
                            content_counts = node["content_counts"]
                            if isinstance(content_counts, list):
                                print(f"  content_counts: list with {len(content_counts)} elements")
                                print(f"  First 5 elements: {content_counts[:5]}")
                            else:
                                print(f"  content_counts: {content_counts}")
                        
                        if "lengths" in node:
                            print(f"  lengths: {node.get('lengths')}")
                
                print("\n" + "="*80)
                print("TESTING OUR LOGIC")
                print("="*80)
                
                # Simulate our logic
                nodes = schema.get("nodes", [])
                default_node = None
                
                # First pass: look for explicit default=true
                for node in nodes:
                    if node.get("default", False):
                        default_node = node
                        print(f"\nFound default node (explicit): {node.get('title', 'NO TITLE')} / key={node.get('key', '')}")
                        break
                
                # If no explicit default, treat the first JaggedArrayNode with empty title as default
                if not default_node:
                    for node in nodes:
                        if node.get("nodeType") == "JaggedArrayNode":
                            node_title = node.get("title", "")
                            node_key = node.get("key", "")
                            if not node_title or node_key == "default":
                                default_node = node
                                print(f"\nFound default node (implicit): {node.get('title', 'NO TITLE')} / key={node.get('key', '')}")
                                break
                
                # Now separate other nodes
                other_nodes = [n for n in nodes if n != default_node]
                
                print(f"\nDefault node: {default_node.get('title', 'NO TITLE') if default_node else 'NONE'}")
                print(f"Other nodes: {len(other_nodes)}")
                for node in other_nodes:
                    print(f"  - {node.get('title', 'NO TITLE')}")
                
                if default_node:
                    print(f"\n--- Processing default node ---")
                    section_names = default_node.get("sectionNames", [])
                    he_section_names = default_node.get("heSectionNames", [])
                    
                    # Get lengths
                    if "content_counts" in default_node:
                        content_counts = default_node["content_counts"]
                        if isinstance(content_counts, list) and content_counts:
                            lengths = [len(content_counts)]
                            print(f"Using content_counts: {len(content_counts)} sections")
                        else:
                            lengths = default_node.get("lengths", [])
                            print(f"Using lengths field: {lengths}")
                    else:
                        lengths = default_node.get("lengths", [])
                        print(f"Using lengths field: {lengths}")
                    
                    print(f"Section names: {section_names}")
                    print(f"Hebrew section names: {he_section_names}")
                    print(f"Lengths: {lengths}")
                    
                    if lengths and len(lengths) > 0:
                        num_sections = lengths[0]
                        print(f"\nWould create {num_sections} children (Simanim 1-{num_sections})")
                    else:
                        print("\nWARNING: No lengths found, would create 0 children!")
                
            else:
                print(f"Failed to fetch: {response.status}")

if __name__ == "__main__":
    asyncio.run(debug_even_haezer())
