import json

with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

talmud = next((c for c in tree if c['title'] == 'Talmud'), None)
if talmud:
    bavli = next((c for c in talmud['children'] if c['title'] == 'Bavli'), None)
    if bavli:
        zeraim = next((c for c in bavli['children'] if 'Zeraim' in c['title']), None)
        if zeraim:
            print(f"Seder Zeraim: {zeraim['title']}")
            print(f"Children ({len(zeraim['children'])}):") 
            for child in zeraim['children']:
                print(f"  - {child['title']} ({child['heTitle']}) - {len(child['children'])} children")
                if len(child['children']) > 0:
                    print(f"    First 3:")
                    for c in child['children'][:3]:
                        print(f"      - {c['title']} ({c['heTitle']})")
