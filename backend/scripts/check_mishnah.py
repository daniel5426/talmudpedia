import json

with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

mishnah = next((c for c in tree if c['title'] == 'Mishnah'), None)
if mishnah:
    print(f"Mishnah has {len(mishnah['children'])} children:")
    for seder in mishnah['children']:
        print(f"\n{seder['title']} ({seder['heTitle']}):")
        print(f"  {len(seder['children'])} tractates")
        if seder['children']:
            first_tractate = seder['children'][0]
            print(f"  First: {first_tractate['title']} ({first_tractate['heTitle']})")
            print(f"    Children: {len(first_tractate['children'])}")
            if first_tractate['children']:
                print(f"    First 3:")
                for c in first_tractate['children'][:3]:
                    print(f"      - {c['title']} ({c['heTitle']})")
