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
