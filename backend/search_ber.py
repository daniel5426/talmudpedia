import json

# Load the tree
with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

print("=== Searching for Berakhot ===")
talmud = next((c for c in tree if c['title'] == 'Talmud'), None)
if talmud:
    print(f"Talmud has {len(talmud['children'])} children")
    for child in talmud['children']:
        print(f"  - {child['title']}")
        if child['title'] == 'Bavli':
            bebavli = child['children']
            print(f"    Bavli has {len(child['children'])} books")
            ber = next((b for b in child['children'] if b['title'] == 'Berakhot'), None)
            if ber:
                print(f"\n    Berakhot found!")
                print(f"    Title: {ber['title']}")
                print(f"    HeTitle: {ber['heTitle']}")
                print(f"    Children: {len(ber['children'])}")
                if ber['children']:
                    print(f"    First few children:")
                    for c in ber['children'][:5]:
                        print(f"      - {c}")

print("\n\n=== Searching for Shulchan Arukh ===")
halakhah = next((c for c in tree if c['title'] == 'Halakhah'), None)
if halakhah:
    for child in halakhah['children']:
        if 'Shulchan Arukh' in child['title']:
            print(f"\nFound: {child['title']}")
            print(f"HeTitle: {child['heTitle']}")
            print(f"Children: {len(child['children'])}")
            if child['children']:
                print(f"First 5 children:")
                for c in child['children'][:5]:
                    print(f"  - {c['title']} / {c['heTitle']}")
            break
