import json

# Load the tree
with open("backend/sefaria_tree.json", "r", encoding="utf-8") as f:
    tree = json.load(f)

print("=== Top-level categories ===")
for cat in tree:
    print(f"- {cat['title']} ({cat['heTitle']})")

print("\n=== Sample: Tanakh > Torah > Genesis ===")
tanakh = next((c for c in tree if c['title'] == 'Tanakh'), None)
if tanakh:
    torah = next((c for c in tanakh['children'] if c['title'] == 'Torah'), None)
    if torah:
        genesis = next((c for c in torah['children'] if c['title'] == 'Genesis'), None)
        if genesis:
            print(f"Title: {genesis['title']}")
            print(f"HeTitle: {genesis['heTitle']}")
            print(f"Ref: {genesis['ref']}")
            print(f"HeRef: {genesis.get('heRef', 'N/A')}")
            print(f"Best Hebrew Version: {genesis.get('bestHebrewVersion', 'N/A')}")
            print(f"Children count: {len(genesis['children'])}")
            if genesis['children']:
                print(f"First child: {genesis['children'][0]}")
                print(f"Last child: {genesis['children'][-1]}")

print("\n=== Sample: Talmud > Bavli > Berakhot ===")
talmud = next((c for c in tree if c['title'] == 'Talmud'), None)
if talmud:
    bavli = next((c for c in talmud['children'] if c['title'] == 'Bavli'), None)
    if bavli:
        berakhot = next((c for c in bavli['children'] if c['title'] == 'Berakhot'), None)
        if berakhot:
            print(f"Title: {berakhot['title']}")
            print(f"HeTitle: {berakhot['heTitle']}")
            print(f"Ref: {berakhot['ref']}")
            print(f"HeRef: {berakhot.get('heRef', 'N/A')}")
            print(f"Children count: {len(berakhot['children'])}")
            if berakhot['children']:
                print(f"First child: {berakhot['children'][0]}")
                print(f"Last child: {berakhot['children'][-1]}")

print("\n=== Sample: Halakhah > Shulchan Arukh ===")
halakhah = next((c for c in tree if c['title'] == 'Halakhah'), None)
if halakhah:
    sa = next((c for c in halakhah['children'] if c['title'] == 'Shulchan Arukh, Orach Chayim'), None)
    if sa:
        print(f"Title: {sa['title']}")
        print(f"HeTitle: {sa['heTitle']}")
        print(f"Ref: {sa['ref']}")
        print(f"HeRef: {sa.get('heRef', 'N/A')}")
        print(f"Children count: {len(sa['children'])}")
        if sa['children']:
            print(f"First 3 children:")
            for child in sa['children'][:3]:
                print(f"  - {child}")

print("\n=== Sample: Midrash > Aggadah > Midrash Rabbah ===")
midrash = next((c for c in tree if c['title'] == 'Midrash'), None)
if midrash:
    aggadah = next((c for c in midrash['children'] if c['title'] == 'Aggadah'), None)
    if aggadah:
        mr = next((c for c in aggadah['children'] if c['title'] == 'Midrash Rabbah'), None)
        if mr:
            esther_rabbah = next((c for c in mr['children'] if c['title'] == 'Esther Rabbah'), None)
            if esther_rabbah:
                print(f"Title: {esther_rabbah['title']}")
                print(f"HeTitle: {esther_rabbah['heTitle']}")
                print(f"Ref: {esther_rabbah['ref']}")
                print(f"HeRef: {esther_rabbah.get('heRef', 'N/A')}")
                print(f"Children count: {len(esther_rabbah['children'])}")
                if esther_rabbah['children']:
                    print(f"First 3 children:")
                    for child in esther_rabbah['children'][:3]:
                        print(f"  - {child['title']} / {child['heTitle']}")
