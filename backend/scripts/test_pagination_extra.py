
    print("\nTest 7: SMG Remazim -> Mitzvah 1 (Forward Navigation through Default Node)")
    # Remazim is just before the main default node (Mitzvot).
    # We want to see if scrolling down from Remazim loads Mitzvah 1.
    
    # First, get last page of Remazim?
    # Or just ask for 'next_ref' logic.
    # TextEndpoints doesn't expose get_next directly via API, but get_source_text does logic.
    # We can use get_next_section_ref directly.
    
    print("Fetching next section ref from: Sefer Mitzvot Gadol, Positive Commandments, Remazim")
    # Note: "Remazim" might be the ref for the whole node.
    db = await DatabaseService.get_database()
    doc = await TextService._find_best_document(db, "Sefer Mitzvot Gadol")
    schema = doc.get("schema")
    
    current_ref = "Sefer Mitzvot Gadol, Positive Commandments, Remazim"
    next_ref = ComplexTextNavigator.get_next_section_ref("Sefer Mitzvot Gadol", schema, current_ref)
    print(f"Calculated Next Ref: {next_ref}")
    
    if next_ref:
         # Try to fetch it
         print(f"Fetching Calculated Next Ref: {next_ref}")
         res = await TextEndpoints.get_source_text(next_ref)
         if res:
             print(f"✅ Success! Loaded next ref. HeRef: {res.get('he_ref')}")
             if "עשין א" in res.get('he_ref', "") or "מצוה א" in str(res.get('segments')):
                 print("✅ CONFIRMED: Loaded Mitzvah 1 content.")
             else:
                 print(f"⚠️ Warning: HeRef {res.get('he_ref')} does not look like Mitzvah 1.")
         else:
             print("❌ Failed to fetch content for Calculated Next Ref.")
    else:
         print("❌ Failed to calculate next ref.")
         
