import json

# Load the tree
with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

talmud = next((c for c in tree if c['title'] == 'Talmud'), None)
if talmud:
    bavli = next((c for c in talmud['children'] if c['title'] == 'Bavli'), None)
    if bavli:
        print(f"Bavli books ({len(bavli['children'])}):")
        for book in bavli['children']:
            print(f"  - {book['title']} ({book['heTitle']}) - {len(book['children'])} children")
