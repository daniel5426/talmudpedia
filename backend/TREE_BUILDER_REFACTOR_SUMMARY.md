# Tree Builder Refactoring - Summary

## Problem Statement
The original `tree_builder.py` had several critical limitations:
1. **Hardcoded support**: Only worked for 3 categories (Tanakh, Talmud, Shulchan Arukh)
2. **Manual Hebrew titles**: Hebrew titles were hardcoded for only these 3 categories
3. **Manual structure**: Chapter counts were manually defined (e.g., hardcoded list of Tanakh book chapters)
4. **No heRef support**: Hebrew references were not included in the tree
5. **Not extensible**: Could not handle the vast majority of books in the Sefaria database

## Solution Approach

### Database Research
I conducted comprehensive research on the MongoDB structure to understand the schema:

**Key Findings:**
- 69,300 documents have BOTH `schema` and `shape` fields
- 6,962 documents have ONLY `shape` (no `schema`)
- The `schema` field is the authoritative source for:
  - Primary Hebrew titles (`titles` array with `primary: true`)
  - Hebrew section names (`heSectionNames`)
  - Book structure (`lengths`, `depth`, `nodeType`)
  - Complex structures (`nodes` for multi-part works)

### New Implementation

The refactored `tree_builder.py` now:

1. **Prioritizes documents with schema**: Updated `load_data()` to prefer documents that have a `schema` field when deduplicating by title

2. **Extracts Hebrew titles dynamically**: 
   - Uses `get_primary_he_title()` to find the primary Hebrew title from `schema.titles`
   - Falls back to top-level `heTitle` if schema is unavailable

3. **Uses schema structure data**:
   - Extracts `heSectionNames` for Hebrew section labels
   - Uses `lengths` array to determine chapter/section counts
   - Handles different `nodeType` values (JaggedArrayNode, SchemaNode)

4. **Adds heRef support**:
   - Every node now includes both `ref` and `heRef`
   - Hebrew references use Hebrew numerals with proper geresh (׳) and gershayim (״) marks

5. **Generic structure building**:
   - `build_simple_children()`: Handles simple structures (Tanakh, Mishnah, etc.)
   - `build_talmud_children()`: Handles Talmud's unique daf/amud structure
   - `build_complex_children()`: Handles complex works with sub-nodes (e.g., Midrash Rabbah)

6. **Improved Hebrew numeral formatting**:
   - Added geresh (׳) for single letters
   - Added gershayim (״) for multiple letters
   - Properly handles special cases (15 = טו, 16 = טז)

## Results

The new tree builder successfully processes **6,581 unique books** across **14 top-level categories**:
- Tanakh (תנ"ך)
- Mishnah (משנה)
- Talmud (תלמוד)
- Midrash (מדרש)
- Kabbalah (קבלה)
- Halakhah (הלכה)
- Jewish Thought (מחשבת ישראל)
- Responsa (שו"ת)
- Tosefta (תוספתא)
- Liturgy (סדר התפילה)
- Musar (ספרי מוסר)
- Second Temple (בית שני)
- Chasidut (חסידות)
- Reference (מילונים וספרי יעץ)

### Verified Examples:

**Genesis (Tanakh)**:
- 50 chapters correctly generated
- Hebrew title: בראשית
- Hebrew references: e.g., "בראשית א׳" (Genesis 1)

**Berakhot (Talmud)**:
- 125 dapim (pages) correctly generated
- Hebrew title: ברכות  
- Hebrew references: e.g., "דף ב׳." (Daf 2a), "דף ב׳:" (Daf 2b)

**Mishnah Berakhot**:
- 9 chapters correctly generated
- Hebrew title: משנה ברכות
- Hebrew references: e.g., "פרק א׳" (Chapter 1)

**Esther Rabbah (Complex structure)**:
- 2 sub-sections: Petichta (פתיחתא) and main text
- Properly handles `schema.nodes` structure

## Technical Details

### Schema Structure Used:
```python
{
  "nodeType": "JaggedArrayNode",  # or "SchemaNode"
  "depth": 2,
  "lengths": [50, 1533],  # [chapters, verses]
  "sectionNames": ["Chapter", "Verse"],
  "heSectionNames": ["פרק", "פסוק"],
  "titles": [
    {"text": "Bereshit", "lang": "en"},
    {"text": "בראשית", "lang": "he", "primary": true},
    {"text": "Genesis", "lang": "en", "primary": true}
  ]
}
```

### Hebrew Reference Format:
- Single digit: א׳, ב׳, ג׳
- Multiple digits: יא״ב (12), כ״ג (23), etc.
- Talmud: דף ב׳. (2a), דף ב׳: (2b)

## Next Steps

The tree is now ready to be used by the frontend. Future enhancements could include:
1. Caching the tree to avoid regeneration
2. Incremental updates when new books are added
3. Additional metadata (descriptions, publication dates, etc.)
4. Support for alternate structures (e.g., Parasha divisions)
