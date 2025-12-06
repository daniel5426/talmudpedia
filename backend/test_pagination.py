
import asyncio
import sys
import os
from unittest.mock import MagicMock

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

# MOCK PROBLEM MODULES BEFORE IMPORTING
sys.modules["app.agent"] = MagicMock()
sys.modules["app.agent.factory"] = MagicMock()
sys.modules["app.endpoints.agent"] = MagicMock()

import asyncio
import os
from app.endpoints.texts import TextEndpoints, TextService, ComplexTextNavigator
# from app.services.database import DatabaseService
from app.db.connection import MongoDatabase

async def test_ref(ref, pages_after=0):
    print(f"\n--- Testing: {ref} ---")
    try:
        result = await TextEndpoints.get_source_text(ref, pages_after=pages_after)
        print(f"✅ Success! Keys: {list(result.keys())}")
        if result.get('pages'):
             print(f"Pages returned: {len(result['pages'])}")
             for p in result['pages']:
                 print(f" - Ref: {p['ref']}")
                 print(f" - HeRef: {p.get('he_ref')}")
        
        if result.get("he_ref"):
             print(f"Top Level HeRef: {result['he_ref']}")

        return result
    except Exception as e:
        print(f"❌ Failed with error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    # Connect to DB
    await MongoDatabase.connect()
    
    # 1. Original Pagination Test
    print("Test 1: Pagination Chain")
    # Start at 1
    res1 = await test_ref("Sefer Mitzvot Gadol, Positive Commandments 1", pages_after=0)
    
    if res1 and res1['can_load_more']['bottom']:
        print("Fetching next from Page 1 ref...")
        # Simulate frontend requesting next pages from current ref
        res2 = await test_ref("Sefer Mitzvot Gadol, Positive Commandments 1", pages_after=2)
        # Should return 1, 2, 3
        
        # Verify Page 3 exists
        if len(res2['pages']) >= 3:
            page3_ref = res2['pages'][2]['ref']
            print(f"Got Page 3: {page3_ref}")
            
            # Simulate scrolling to Page 3 and loading more
            print(f"Fetching next from {page3_ref}...")
            res3 = await test_ref(page3_ref, pages_after=2)
            # Should return 3, 4, 5
        else:
            print("❌ Failed to get 3 pages in second step.")

    # 2. KeyError Regression Test
    print("\nTest 2: KeyError Regression (Rabbinic Commandments)")
    await test_ref("Sefer Mitzvot Gadol, Rabbinic Commandments, Laws of Tisha B'Av", pages_after=2)

    print("\nTest 3: Inter-Node Pagination (Introduction -> Remazim)")
    intro_ref = "Sefer Mitzvot Gadol, Positive Commandments, Introduction"
    print(f"Fetching: {intro_ref}")
    try:
         # Intro has 1 segment? Requesting pages_after=5 should trigger next section load.
         res_intro = await test_ref(intro_ref, pages_after=5)
         
         # Check if we got Remazim
         found_remazim = False
         if res_intro and res_intro.get("pages"):
             for p in res_intro["pages"]:
                 if "Remazim" in p["ref"]:
                     print(f"✅ Found Next Section Page: {p['ref']}")
                     found_remazim = True
                     
         if not found_remazim:
             print("❌ Failed to auto-load Remazim from Introduction.")
             
    except Exception as e:
        print(f"❌ Failed Test 3: {e}")
        import traceback
        traceback.print_exc()

    print("\nTest 4: Minchat Chinukh (Implicit Default Node) - Should Resolve")
    result = await test_ref("Minchat Chinukh 1")
    if result:
        print(f"✅ Success! Resolved 'Minchat Chinukh 1'. Main HeRef: {result.get('he_ref')}")
        if result.get("pages"):
             print(f" - First Page Ref: {result['pages'][0].get('ref')}")
    else:
        print(f"❌ Failed to retrieve 'Minchat Chinukh 1'.")

    print("\nTest 5: Colon Ref Regression (Positive Commandments:2) - Should Resolve")
    result = await test_ref("Sefer Mitzvot Gadol, Positive Commandments:2")
    if result:
         print(f"✅ Success! Resolved 'Positive Commandments:2'. Main HeRef: {result.get('he_ref')}")

    print("\nTest 6: Backward Inter-Node (Remazim -> Introduction)")
    # Scrolling UP from Remazim should load Introduction
    # Requires pages_before > 0
    res_back = await test_ref("Sefer Mitzvot Gadol, Positive Commandments, Remazim", pages_after=0)
    # Wait, need to pass pages_before. My test_ref helper doesn't support pages_before kwarg yet.
    # Let's verify manually using TextEndpoints directly or update helper?
    # Updating helper is cleaner but let's just use TextEndpoints here.
    
    print("Fetching Remazim with pages_before=2...")
    try:
        result = await TextEndpoints.get_source_text("Sefer Mitzvot Gadol, Positive Commandments, Remazim", pages_before=2)
        
        if result and len(result["pages"]) > 1:
            print("✅ Success! Loaded Previous Section (Introduction) when scrolling up from Remazim.")
            for p in result["pages"]:
                 print(f" - {p['ref']}")
        else:
            print("❌ Failed! Did not find both Introduction and Remazim.")
            if result:
                 print(f" - {result['pages'][0]['ref']}")

    except Exception as e:
        print(f"❌ Failed Test 6: {e}")

    print("\nTest 7: SMG Remazim -> Mitzvah 1 (Forward Navigation through Default Node)")
    # Remazim is just before the main default node (Mitzvot).
    # We want to see if scrolling down from Remazim loads Mitzvah 1.
    
    db = MongoDatabase.get_db()
    index_doc = await db.index.find_one({"title": "Sefer Mitzvot Gadol"})
    schema = index_doc.get("schema")
    
    # Note: Using the specific LAST page of Remazim would be more realistic for pagination.
    # But get_next_section_ref should work on the section level Ref too.
    current_ref = "Sefer Mitzvot Gadol, Positive Commandments, Remazim"
    next_ref = ComplexTextNavigator.get_next_section_ref("Sefer Mitzvot Gadol", schema, current_ref)
    print(f"Calculated Next Ref: {next_ref}")
    
    if next_ref:
         # Try to fetch it
         print(f"Fetching Calculated Next Ref: {next_ref}")
         res = await TextEndpoints.get_source_text(next_ref)
         if res:
             print(f"✅ Success! Loaded next ref. Top HeRef: {res.get('he_ref')}")
             # Check if it looks like Mitzvah 1
             # Page 1 he_ref should probably be "Sefer Mitzvot Gadol, Positive Commandments 1" or similar
             first_page = res['pages'][0]
             print(f" - First Page Ref: {first_page.get('ref')}")
             print(f" - First Page HeRef: {first_page.get('he_ref')}")
             
             if "1" in first_page.get('ref', ""):
                 print("✅ CONFIRMED: Loaded Mitzvah 1 content.")
             else:
                 print(f"⚠️ Warning: Ref {first_page.get('ref')} does not look like Mitzvah 1.")
         else:
             print("❌ Failed to fetch content for Calculated Next Ref.")
    else:
         print("❌ Failed to calculate next ref.")

    
    print("\nTest 8: SMG Remazim Splitting Check")
    # Request Remazim. Expect 1 page.
    ref = "Sefer Mitzvot Gadol, Positive Commandments, Remazim"
    print(f"Fetching: {ref}")
    try:
        result = await TextEndpoints.get_source_text(ref)
        pages = result.get("pages", [])
        print(f"Pages returned: {len(pages)}")
        if len(pages) == 1:
            print("✅ PASS: Returned 1 page for Remazim (Depth 1).")
        else:
            print(f"❌ FAIL: Expected 1 page for Remazim, got {len(pages)}. First: {pages[0].get('ref')}")
            
    except Exception as e:
        print(f"❌ Failed Test 8: {e}")

    print("\nTest 9: Sefer HaChinukh Dead End Check")
    # Intro -> Mitzvah 1. Mitzvah 1 is short (Depth 1?).
    # If we fetch Intro with pages_after=50, it should load Mitzvah 1 completely.
    # Then can_load_bottom MUST be True (for Mitzvah 2).
    
    ref_intro = "Sefer HaChinukh, Opening Letter, Opening Letter by the Author"
    print(f"Fetching: {ref_intro} with pages_after=50") 
    
    try:
        result = await TextEndpoints.get_source_text(ref_intro, pages_after=50)
        can_load_bottom = result.get("can_load_more", {}).get("bottom")
        pages = result.get("pages", [])
        
        # Check if Mitzvah 1 is in pages
        mitzvah_1_pages = [p for p in pages if "Mitzvah 1" in p['ref'] or "Commandment 1" in p['ref'] or  "מצוה א" in p['he_ref']]
        if mitzvah_1_pages:
             print(f"Loaded {len(mitzvah_1_pages)} page(s) of Mitzvah 1.")
             print(f"Last Page Ref: {pages[-1]['ref']}")
             print(f"Last Page HeRef: {pages[-1]['he_ref']}")
        
        print(f"Can Load Bottom: {can_load_bottom}")
        if can_load_bottom:
             print("✅ PASS: can_load_bottom is True (System knows Mitzvah 2 exists).")
        else:
             print("❌ FAIL: can_load_bottom is False. System thinks text ends at Mitzvah 1.")

    except Exception as e:
        print(f"❌ Failed Test 9: {e}")

    print("\nTest 10: Scroll Down Integrity (Introduction -> Remazim)")
    # Should bundle Remazim into 1 page.
    ref = "Sefer Mitzvot Gadol, Positive Commandments, Introduction"
    print(f"Fetching: {ref} + pages_after=50")
    
    try:
        result = await TextEndpoints.get_source_text(ref, pages_after=50)
        pages = result.get("pages", [])
        
        remazim_pages = [p for p in pages if "Remazim" in p['ref'] or "רמזים" in p['he_ref']]
        
        if len(remazim_pages) == 1:
            print("✅ PASS: Remazim is BUNDLED into one page during scroll.")
            print(f" - Ref: {remazim_pages[0]['ref']}")
        elif len(remazim_pages) > 1:
             print(f"❌ FAIL: Remazim is SPLIT into {len(remazim_pages)} pages.")
        else:
             print("⚠️ WARNING: Remazim not loaded.")

    except Exception as e:
         print(f"❌ Failed Test 10: {e}")

if __name__ == "__main__":
    asyncio.run(main())
