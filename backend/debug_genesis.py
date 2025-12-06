import json

# Load the tree
with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

tanakh = next((c for c in tree if c['title'] == 'Tanakh'), None)
if tanakh:
    torah = next((c for c in tanakh['children'] if c['title'] == 'Torah'), None)
    if torah:
        genesis = next((c for c in torah['children'] if c['title'] == 'Genesis'), None)
        if genesis:
            print("Full Genesis node:")
            print(json.dumps(genesis, indent=2, ensure_ascii=False))
